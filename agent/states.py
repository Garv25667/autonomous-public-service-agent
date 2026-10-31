import time
import uuid
from typing import Literal, List, Optional, Dict, Any
from pydantic import BaseModel, Field


StatusType = Literal["running", "needs_human", "failed", "done"]
StepStatus = Literal["pending", "in_progress", "completed", "failed", "skipped"]


class AuditEvent(BaseModel):
    """Immutable audit log entry recording each action taken by the agent."""
    timestamp: float = Field(default_factory=time.time)
    step_id: str
    action: str  # e.g., 'goto', 'fill', 'click', 'select_option', 'upload', 'verify'
    selector: Optional[str] = None
    value_summary: Optional[str] = None  # Redacted/summarized for sensitive fields
    status: Literal["success", "failure", "warning"] = "success"
    screenshot_path: Optional[str] = None
    error_message: Optional[str] = None


class PlanStep(BaseModel):
    """A typed, discrete step in the service application workflow."""
    step_id: str
    name: str
    intent: str
    expected_url_pattern: Optional[str] = None
    status: StepStatus = "pending"
    retries: int = 0
    data_keys: List[str] = Field(default_factory=list)


class RunState(BaseModel):
    """
    Core state object for the agent runtime adhering to the 48-Hour Build Playbook:
    - Checkpointed to SQLite after every step for crash recovery
    - Tracks global action budget, loop detection page hashes, and audit events
    - Pauses in 'needs_human' state for CAPTCHA/OTP or final submission review
    """
    run_id: str = Field(default_factory=lambda: f"run_{uuid.uuid4().hex[:10]}")
    portal_id: str = "scholarship_portal"
    service: str = "scholarship_application"
    status: StatusType = "running"
    plan: List[PlanStep] = Field(default_factory=list)
    step_index: int = 0
    retries_on_step: int = 0
    total_actions: int = 0  # Global action budget counter
    seen_page_hashes: List[str] = Field(default_factory=list)  # Loop detection
    llm_calls: int = 0
    submitted: bool = False
    receipt_id: Optional[str] = None
    audit: List[AuditEvent] = Field(default_factory=list)
    human_reason: Optional[str] = None  # Reason when status is 'needs_human'

    @property
    def current_step(self) -> Optional[PlanStep]:
        if 0 <= self.step_index < len(self.plan):
            return self.plan[self.step_index]
        return None

    def record_audit(
        self,
        action: str,
        selector: Optional[str] = None,
        value_summary: Optional[str] = None,
        status: Literal["success", "failure", "warning"] = "success",
        screenshot_path: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> AuditEvent:
        step_id = self.current_step.step_id if self.current_step else "init"
        event = AuditEvent(
            step_id=step_id,
            action=action,
            selector=selector,
            value_summary=value_summary,
            status=status,
            screenshot_path=screenshot_path,
            error_message=error_message
        )
        self.audit.append(event)
        self.total_actions += 1
        return event
