import sqlite3
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
from .states import RunState


class Checkpointer:
    """
    Persists RunState to a local SQLite database after every action.
    Enables instant crash recovery, offline auditing, and resuming from human pauses (CAPTCHA/OTP).
    """

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            # Default to <repo_root>/data/agent_runs.sqlite
            self.db_path = Path(__file__).resolve().parents[1] / "data" / "agent_runs.sqlite"
        else:
            self.db_path = Path(db_path)

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connection(self):
        """Context manager that guarantees connection is closed on Windows."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS checkpoints (
                    run_id TEXT PRIMARY KEY,
                    portal_id TEXT NOT NULL,
                    service TEXT NOT NULL,
                    status TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    submitted INTEGER NOT NULL DEFAULT 0,
                    receipt_id TEXT,
                    state_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_status ON checkpoints(status);
            """)
            conn.commit()

    def save(self, state: RunState) -> None:
        """Saves or updates the current RunState in SQLite."""
        state_json = state.model_dump_json()
        with self._connection() as conn:
            conn.execute("""
                INSERT INTO checkpoints (
                    run_id, portal_id, service, status, step_index,
                    submitted, receipt_id, state_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(run_id) DO UPDATE SET
                    status=excluded.status,
                    step_index=excluded.step_index,
                    submitted=excluded.submitted,
                    receipt_id=excluded.receipt_id,
                    state_json=excluded.state_json,
                    updated_at=CURRENT_TIMESTAMP;
            """, (
                state.run_id,
                state.portal_id,
                state.service,
                state.status,
                state.step_index,
                1 if state.submitted else 0,
                state.receipt_id,
                state_json
            ))
            conn.commit()

    def load(self, run_id: str) -> Optional[RunState]:
        """Loads a RunState from SQLite by run_id."""
        with self._connection() as conn:
            cursor = conn.execute(
                "SELECT state_json FROM checkpoints WHERE run_id = ?",
                (run_id,)
            )
            row = cursor.fetchone()
            if row:
                return RunState.model_validate_json(row["state_json"])
        return None

    def get_latest_active_run(self) -> Optional[RunState]:
        """Retrieves the most recent run that needs human intervention or is currently running."""
        with self._connection() as conn:
            cursor = conn.execute("""
                SELECT state_json FROM checkpoints
                WHERE status IN ('running', 'needs_human')
                ORDER BY updated_at DESC LIMIT 1
            """)
            row = cursor.fetchone()
            if row:
                return RunState.model_validate_json(row["state_json"])
        return None

    def list_runs(self) -> List[Dict[str, Any]]:
        """Returns a list of all recorded runs."""
        with self._connection() as conn:
            cursor = conn.execute("""
                SELECT run_id, portal_id, service, status, step_index, submitted, receipt_id, updated_at
                FROM checkpoints ORDER BY updated_at DESC
            """)
            return [dict(row) for row in cursor.fetchall()]
