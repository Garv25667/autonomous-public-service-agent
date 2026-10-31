import hashlib
import time
from typing import Optional
from .states import RunState


class GuardViolation(Exception):
    """Base exception for all agent runtime safety guard violations."""
    pass


class LoopDetectedError(GuardViolation):
    """Raised when the agent gets stuck on the same page state 3 times consecutively."""
    pass


class ActionBudgetExceededError(GuardViolation):
    """Raised when total browser actions exceed the global safety limit."""
    pass


class StepRetryExceededError(GuardViolation):
    """Raised when retries on a single step exceed the allowable threshold."""
    pass


class DoubleSubmissionError(GuardViolation):
    """Raised to prevent duplicate submissions when an application receipt already exists."""
    pass


class WallClockTimeoutError(GuardViolation):
    """Raised when total execution duration exceeds the maximum allowed time."""
    pass


class RuntimeGuards:
    """
    Enforces the safety guards outlined in Section 2 & 4 of the 48-Hour Build Playbook:
    1. Loop Detection: Escalate if same page hash is seen 3 times in a row.
    2. Step Retry Cap: Max 3 retries per step.
    3. Global Action Budget: Max 80 browser actions per run.
    4. Idempotency: Ensure an already submitted application is never submitted twice.
    5. Wall-Clock Timeout: Max runtime in seconds.
    """

    def __init__(
        self,
        max_action_budget: int = 80,
        max_step_retries: int = 3,
        loop_threshold: int = 3,
        wall_clock_timeout_sec: float = 300.0,
    ):
        self.max_action_budget = max_action_budget
        self.max_step_retries = max_step_retries
        self.loop_threshold = loop_threshold
        self.wall_clock_timeout_sec = wall_clock_timeout_sec
        self.start_time = time.time()

    @staticmethod
    def compute_page_hash(url: str, text_snapshot: str = "") -> str:
        """Computes a deterministic hash from URL pattern and page contents."""
        normalized = f"{url.strip().lower()}:::{text_snapshot.strip()}"
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]

    def check_action_budget(self, state: RunState) -> None:
        """Ensure the agent has not exceeded the total global action allowance."""
        if state.total_actions >= self.max_action_budget:
            raise ActionBudgetExceededError(
                f"Global action budget exceeded ({state.total_actions}/{self.max_action_budget}). Halting agent."
            )

    def check_step_retry(self, state: RunState) -> None:
        """Ensure the agent does not retry the same step indefinitely."""
        if state.retries_on_step >= self.max_step_retries:
            step_name = state.current_step.name if state.current_step else "unknown"
            raise StepRetryExceededError(
                f"Step '{step_name}' exceeded retry limit ({state.retries_on_step}/{self.max_step_retries})."
            )

    def record_and_check_loop(self, state: RunState, page_hash: str) -> None:
        """
        Records the current page hash and checks if the last N page hashes are identical.
        Triggers LoopDetectedError if the agent is stuck in an infinite cycle.
        """
        state.seen_page_hashes.append(page_hash)

        if len(state.seen_page_hashes) >= self.loop_threshold:
            recent_hashes = state.seen_page_hashes[-self.loop_threshold:]
            if len(set(recent_hashes)) == 1:
                raise LoopDetectedError(
                    f"Infinite loop detected: Page hash '{page_hash}' observed {self.loop_threshold} times in a row."
                )

    def check_idempotency(self, state: RunState) -> None:
        """Prevent double-submission if the run has already been recorded as submitted."""
        if state.submitted or state.receipt_id:
            raise DoubleSubmissionError(
                f"Application already submitted with receipt ID: {state.receipt_id}. Aborting duplicate submission."
            )

    def check_timeout(self) -> None:
        """Check wall-clock runtime limit."""
        elapsed = time.time() - self.start_time
        if elapsed > self.wall_clock_timeout_sec:
            raise WallClockTimeoutError(
                f"Execution wall-clock timeout exceeded ({elapsed:.1f}s > {self.wall_clock_timeout_sec}s)."
            )

    def verify_all(self, state: RunState) -> None:
        """Runs all universal checks before executing an action."""
        self.check_timeout()
        self.check_action_budget(state)
        self.check_step_retry(state)
