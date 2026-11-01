"""
Workflow Replay Cache (agent/workflow_cache.py)
Implements Section 4 (Phase 2 Stretch) of the 48-Hour Build Playbook:
Explore-Once-Then-Replay Engine with self-healing and zero LLM quota on warm runs.
"""

import sqlite3
import hashlib
import json
import time
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from contextlib import contextmanager
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]


class CachedStep(BaseModel):
    """A single deterministic browser action stored for replay."""
    step_id: str
    intent: str
    action_type: str  # "fill", "select", "check", "upload", "click"
    locator_strategy: str  # "label", "role", "css", "id"
    locator_target: str
    value_ref: Optional[str] = None  # Reference path into profile, e.g. "personal.full_name"
    literal_value: Optional[str] = None
    success_count: int = 1
    last_verified_at: float = Field(default_factory=time.time)


class WorkflowRecord(BaseModel):
    """A sequence of cached steps associated with a specific page fingerprint."""
    page_fingerprint: str
    portal_id: str = "scholar_portal"
    url_pattern: str
    steps: List[CachedStep] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)


class WorkflowCache:
    """
    Manages recording and replaying deterministic browser workflows.
    Reduces LLM calls to 0 on warm runs and self-heals when portal DOM changes.
    """

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            self.db_path = ROOT / "data" / "workflow_cache.sqlite"
        else:
            self.db_path = Path(db_path)

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_hits: int = 0
        self.cache_misses: int = 0
        self.healed_steps: int = 0
        self._init_db()

    @contextmanager
    def _connection(self):
        """Context manager guaranteeing connection closure on Windows."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS workflows (
                    fingerprint TEXT PRIMARY KEY,
                    portal_id TEXT NOT NULL,
                    url_pattern TEXT NOT NULL,
                    steps_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
            """)
            conn.commit()

    @staticmethod
    def compute_page_fingerprint(url_pattern: str, field_labels: List[str]) -> str:
        """
        Computes deterministic SHA-256 fingerprint:
        hash(normalized_url + sorted lowercase labels).
        """
        clean_url = url_pattern.split("?")[0].strip().lower()
        sorted_labels = "::".join(sorted(l.strip().lower() for l in field_labels if l.strip()))
        raw = f"{clean_url}|{sorted_labels}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def get_workflow(self, fingerprint: str) -> Optional[WorkflowRecord]:
        """Retrieves cached workflow for a given fingerprint."""
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM workflows WHERE fingerprint = ?",
                (fingerprint,)
            ).fetchone()

            if not row:
                self.cache_misses += 1
                return None

            self.cache_hits += 1
            data = json.loads(row["steps_json"])
            steps = [CachedStep(**s) for s in data]
            return WorkflowRecord(
                page_fingerprint=row["fingerprint"],
                portal_id=row["portal_id"],
                url_pattern=row["url_pattern"],
                steps=steps,
                created_at=row["created_at"],
                updated_at=row["updated_at"]
            )

    def save_workflow(self, record: WorkflowRecord) -> None:
        """Saves or updates a workflow record."""
        steps_json = json.dumps([s.model_dump() for s in record.steps])
        with self._connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO workflows (
                    fingerprint, portal_id, url_pattern, steps_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                record.page_fingerprint,
                record.portal_id,
                record.url_pattern,
                steps_json,
                record.created_at,
                record.updated_at
            ))
            conn.commit()

    def record_step(
        self,
        fingerprint: str,
        url_pattern: str,
        step: CachedStep,
        portal_id: str = "scholar_portal"
    ) -> None:
        """Appends a successful step to the cached workflow."""
        existing = self.get_workflow(fingerprint)
        now = time.time()

        if existing:
            # Update existing step or append new
            updated = False
            for i, s in enumerate(existing.steps):
                if s.step_id == step.step_id:
                    existing.steps[i] = step
                    existing.steps[i].success_count += 1
                    existing.steps[i].last_verified_at = now
                    updated = True
                    break
            if not updated:
                existing.steps.append(step)
            existing.updated_at = now
            self.save_workflow(existing)
        else:
            new_record = WorkflowRecord(
                page_fingerprint=fingerprint,
                portal_id=portal_id,
                url_pattern=url_pattern,
                steps=[step],
                created_at=now,
                updated_at=now
            )
            self.save_workflow(new_record)

    def heal_step(
        self,
        fingerprint: str,
        step_id: str,
        new_locator_target: str,
        new_strategy: str = "label"
    ) -> bool:
        """
        Self-healing mechanism: updates an obsolete locator in the cache
        after finding element via fallback or perception.
        """
        existing = self.get_workflow(fingerprint)
        if not existing:
            return False

        healed = False
        for s in existing.steps:
            if s.step_id == step_id:
                s.locator_target = new_locator_target
                s.locator_strategy = new_strategy
                s.last_verified_at = time.time()
                healed = True
                break

        if healed:
            existing.updated_at = time.time()
            self.save_workflow(existing)
            self.healed_steps += 1
            return True
        return False

    def invalidate(self, fingerprint: str) -> None:
        """Removes a workflow from cache."""
        with self._connection() as conn:
            conn.execute("DELETE FROM workflows WHERE fingerprint = ?", (fingerprint,))
            conn.commit()

    def clear(self) -> None:
        """Clears all workflows from cache."""
        with self._connection() as conn:
            conn.execute("DELETE FROM workflows")
            conn.commit()
        self.cache_hits = 0
        self.cache_misses = 0
        self.healed_steps = 0

    def get_stats(self) -> Dict[str, Any]:
        """Returns cache telemetry and statistics."""
        with self._connection() as conn:
            count = conn.execute("SELECT COUNT(*) AS cnt FROM workflows").fetchone()["cnt"]

        total_requests = self.cache_hits + self.cache_misses
        hit_rate = (self.cache_hits / total_requests * 100.0) if total_requests > 0 else 0.0

        return {
            "cached_workflows": count,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "hit_rate_percent": round(hit_rate, 1),
            "healed_steps": self.healed_steps,
        }
