from typing import List, Dict, Optional, Literal, Any
from pydantic import BaseModel, Field

from .states import RunState


class ReviewField(BaseModel):
    """Entry in the final approval review summary table."""
    field_name: str
    value_submitted: str
    source: str = "citizen.json"
    confidence: float = 1.0


class ReviewSummaryTable(BaseModel):
    """
    Summary table required by Feature F6 before the final submit click:
    Shows field, value submitted, source, and confidence score.
    """
    fields: List[ReviewField] = Field(default_factory=list)

    def add_field(self, name: str, value: str, source: str = "citizen.json", confidence: float = 1.0):
        self.fields.append(
            ReviewField(
                field_name=name,
                value_submitted=str(value),
                source=source,
                confidence=confidence
            )
        )

    def format_text(self) -> str:
        """Renders summary table as an aligned ASCII text table."""
        header = f"{'FIELD':<25} | {'VALUE SUBMITTED':<30} | {'SOURCE':<15} | {'CONFIDENCE':<10}"
        separator = "-" * len(header)
        rows = [header, separator]
        for f in self.fields:
            val = (f.value_submitted[:27] + "...") if len(f.value_submitted) > 30 else f.value_submitted
            rows.append(f"{f.field_name:<25} | {val:<30} | {f.source:<15} | {f.confidence:<10.2f}")
        return "\n".join(rows)

    def format_markdown(self) -> str:
        """Renders summary table as a markdown table."""
        lines = [
            "| Field | Value Submitted | Source | Confidence |",
            "|---|---|---|---|",
        ]
        for f in self.fields:
            lines.append(f"| **{f.field_name}** | `{f.value_submitted}` | {f.source} | {f.confidence:.2f} |")
        return "\n".join(lines)


class ApprovalResult(BaseModel):
    approved: bool
    status: Literal["approved", "rejected", "dry_run_halted", "awaiting_approval"]
    reason: str


class ApprovalGate:
    """
    Implements Feature F6: Final-submit approval gate from the 48-Hour Playbook:
    1. Compiles and displays a summary table: field, value, source, confidence.
    2. Strict approval requirement: Cannot be bypassed silently.
    3. Dry-run mode: Halts before the final submit click when dry_run=True.
    """

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run

    def build_summary_from_profile(self, profile: Dict[str, Any]) -> ReviewSummaryTable:
        """Constructs a review table directly from citizen.json data."""
        table = ReviewSummaryTable()
        personal = profile.get("personal", {})
        education = profile.get("education", {})

        # Personal details
        table.add_field("Full Name", personal.get("full_name", ""), "citizen.json / personal")
        table.add_field("Date of Birth", personal.get("dob", ""), "citizen.json / personal")
        table.add_field("Category", personal.get("category", ""), "citizen.json / personal")
        table.add_field("Current Course", personal.get("course", ""), "citizen.json / personal")
        table.add_field("State", personal.get("state", ""), "citizen.json / personal")
        table.add_field("District", personal.get("district", ""), "citizen.json / personal")
        table.add_field("Block / Taluka", personal.get("block", ""), "citizen.json / personal")

        # Education details
        table.add_field("College", education.get("college", ""), "citizen.json / education")
        table.add_field("Course Year", education.get("course_year", ""), "citizen.json / education")
        table.add_field("Marks (%)", education.get("marks", ""), "citizen.json / education")
        table.add_field("Annual Income (₹)", education.get("annual_income", ""), "citizen.json / education")
        table.add_field("Marksheet File", education.get("marksheet_path", ""), "citizen.json / education")

        return table

    def evaluate_gate(
        self,
        summary: ReviewSummaryTable,
        explicit_approval: Optional[bool] = None,
        state: Optional[RunState] = None
    ) -> ApprovalResult:
        """
        Evaluates the approval gate strictly adhering to safety rules:
        - Dry-run flag takes precedence -> always stops before submission.
        - explicit_approval is required (cannot be bypassed).
        """
        # 1. Dry run guard
        if self.dry_run:
            if state:
                state.record_audit(
                    action="dry_run_gate",
                    status="warning",
                    value_summary="Dry-run active: submission halted before final click."
                )
            return ApprovalResult(
                approved=False,
                status="dry_run_halted",
                reason="Dry-run flag enabled. Stopped prior to final submission."
            )

        # 2. Check for missing explicit approval (cannot be bypassed)
        if explicit_approval is None:
            if state:
                state.status = "needs_human"
                state.human_reason = "Final approval required before submission."
                state.record_audit(action="approval_gate", status="warning", value_summary="Awaiting human approval")
            return ApprovalResult(
                approved=False,
                status="awaiting_approval",
                reason="Explicit human approval is required before submission."
            )

        # 3. Explicit rejection
        if explicit_approval is False:
            if state:
                state.record_audit(action="approval_gate", status="failure", value_summary="User rejected submission")
            return ApprovalResult(
                approved=False,
                status="rejected",
                reason="Submission was explicitly cancelled by the user."
            )

        # 4. Explicit approval
        if state:
            state.record_audit(action="approval_gate", status="success", value_summary="User approved final submission")

        return ApprovalResult(
            approved=True,
            status="approved",
            reason="User explicitly approved the application for final submission."
        )

    def request_approval(
        self,
        summary: ReviewSummaryTable,
        explicit_approval: Optional[bool] = None,
        state: Optional[RunState] = None
    ) -> ApprovalResult:
        """Convenience alias for evaluate_gate."""
        return self.evaluate_gate(summary, explicit_approval=explicit_approval, state=state)

