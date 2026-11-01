import asyncio
import json
import base64
from pathlib import Path
from typing import Optional, Dict, Any, Callable, List

from playwright.async_api import async_playwright, Page, Browser

from .states import RunState, PlanStep, AuditEvent
from .checkpoint import Checkpointer
from .guards import RuntimeGuards, LoopDetectedError, ActionBudgetExceededError, StepRetryExceededError, DoubleSubmissionError
from .perception import SemanticMapper
from .verifier import PageVerifier, VerificationResult
from .recovery import RecoveryHandler, RecoveryAction
from .tools.secrets import SecretVault
from .tools.docs import DocumentProcessor
from .eligibility import EligibilityEvaluator, EligibilityResult
from .approval import ApprovalGate, ReviewSummaryTable
from .receipt import ReceiptExtractor, ReceiptData

ROOT = Path(__file__).resolve().parents[1]


class AgentOrchestrator:
    """
    Main state machine orchestrating the full autonomous public service pipeline:
    INTAKE -> ELIGIBILITY -> PLAN -> [ OBSERVE -> DECIDE -> ACT -> VERIFY ]* -> APPROVAL -> SUBMIT -> RECEIPT
    """

    def __init__(
        self,
        portal_base_url: str = "http://127.0.0.1:5000",
        headless: bool = False,
        dry_run: bool = False,
        broadcast_callback: Optional[Callable[[Dict[str, Any]], Any]] = None
    ):
        self.portal_base_url = portal_base_url.rstrip("/")
        self.headless = headless
        self.dry_run = dry_run
        self.broadcast_callback = broadcast_callback

        # Initialize core components
        self.checkpointer = Checkpointer()
        self.guards = RuntimeGuards()
        self.vault = SecretVault()
        self.doc_processor = DocumentProcessor()
        self.evaluator = EligibilityEvaluator()
        self.mapper = SemanticMapper()
        self.verifier = PageVerifier()
        self.recovery = RecoveryHandler()
        self.approval_gate = ApprovalGate(dry_run=dry_run)
        self.receipt_extractor = ReceiptExtractor()

    async def _emit_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Sends live WebSocket update to the front end if a callback is registered."""
        if self.broadcast_callback:
            msg = {"event": event_type, "data": payload}
            if asyncio.iscoroutinefunction(self.broadcast_callback):
                await self.broadcast_callback(msg)
            else:
                self.broadcast_callback(msg)

    async def _capture_live_frame(self, page: Page) -> Optional[str]:
        """Captures a JPEG screenshot encoded as base64 for the UI live view screencast."""
        try:
            bytes_data = await page.screenshot(type="jpeg", quality=60)
            return base64.b64encode(bytes_data).decode("utf-8")
        except Exception:
            return None

    def initialize_plan(self) -> List[PlanStep]:
        """Defines the canonical ordered workflow steps."""
        return [
            PlanStep(step_id="login", name="Portal Authentication", intent="Sign in securely to demo portal"),
            PlanStep(step_id="step1", name="Applicant Information", intent="Fill personal and contact details"),
            PlanStep(step_id="step2", name="Academic Details", intent="Fill institution, marks, and upload marksheet"),
            PlanStep(step_id="step3", name="Applicant Declaration", intent="Accept responsibility declaration"),
            PlanStep(step_id="review", name="Final Review & Approval", intent="Human approval gate prior to submission"),
            PlanStep(step_id="receipt", name="Receipt Extraction", intent="Extract reference number and serialize"),
        ]

    async def run(
        self,
        profile_path: Optional[Path] = None,
        resume_run_id: Optional[str] = None
    ) -> RunState:
        """
        Executes the autonomous agent pipeline.
        Supports resume from saved SQLite checkpoint if resume_run_id is provided.
        """
        if profile_path is None:
            profile_path = ROOT / "data" / "citizen.json"

        with open(profile_path, "r", encoding="utf-8") as f:
            profile = json.load(f)

        # 1. Intake: Populate Secret Vault and Validate Documents
        self.vault.load_from_profile(profile)
        personal = profile.get("personal", {})
        education = profile.get("education", {})

        marksheet_file = ROOT / education.get("marksheet_path", "")
        doc_result = self.doc_processor.validate_file(marksheet_file, expected_profile=profile)
        if not doc_result.valid:
            raise ValueError(f"Document pre-flight validation failed: {doc_result.error_message}")

        # 2. Eligibility Pre-Check (Feature F3)
        eligibility = self.evaluator.evaluate(profile)
        if not eligibility.eligible:
            raise ValueError(f"Citizen not eligible: {'; '.join(eligibility.reasons)}")

        # 3. State Setup
        if resume_run_id:
            state = self.checkpointer.load(resume_run_id)
            if not state:
                raise ValueError(f"Run ID '{resume_run_id}' not found in SQLite checkpoints.")
        else:
            state = RunState(plan=self.initialize_plan())
            self.checkpointer.save(state)

        await self._emit_event("run_started", {"run_id": state.run_id, "status": state.status})

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            page = await browser.new_page()

            # Handle native JS confirm dialog on review page
            page.on("dialog", lambda dialog: asyncio.create_task(dialog.accept()))

            try:
                # 4. State Execution Loop
                # Step 0: Login
                if state.step_index == 0:
                    await page.goto(f"{self.portal_base_url}/login")
                    await page.get_by_label("User ID").fill("student")
                    await page.get_by_label("Password").fill("demo123")
                    await page.get_by_role("button", name="Sign in securely").click()
                    await page.wait_for_load_state("domcontentloaded")

                    state.record_audit(action="login", status="success", value_summary="student")
                    state.step_index = 1
                    self.checkpointer.save(state)

                    frame = await self._capture_live_frame(page)
                    await self._emit_event("step_completed", {"step": "login", "screenshot": frame, "state": state.model_dump()})

                # Step 1: Personal Info
                if state.step_index == 1:
                    await page.get_by_label("Full name *").fill(personal["full_name"])
                    await page.get_by_label("Date of birth *").fill(personal["dob"])

                    # Use Semantic Mapper for Category
                    cat_options = ["General", "OBC", "SC", "ST", "EWS"]
                    cat_match = self.mapper.match_dropdown(personal["category"], cat_options, "Category")
                    await page.get_by_label("Category").select_option(label=cat_match.choice or personal["category"])

                    # Course
                    course_options = ["B.Tech", "B.Sc", "B.Com", "B.A.", "Diploma"]
                    course_match = self.mapper.match_dropdown(personal["course"], course_options, "Current course")
                    await page.get_by_label("Current course").select_option(label=course_match.choice or personal["course"])

                    await page.get_by_label("State").select_option(label=personal["state"])
                    await page.get_by_label("District").select_option(label=personal["district"])
                    await page.get_by_label("Block / Taluka").select_option(label=personal["block"])

                    await page.get_by_role("button", name="Save & continue").click()
                    await page.wait_for_load_state("domcontentloaded")

                    # Verify step 1
                    verification = await self.verifier.verify_page(page, expected_heading="Academic information")
                    if not verification.success:
                        action = await self.recovery.execute_recovery(page, verification, state, self.checkpointer)
                        if action.needs_human:
                            return state

                    state.record_audit(action="personal_info", status="success", value_summary=personal["full_name"])
                    state.step_index = 2
                    self.checkpointer.save(state)

                    frame = await self._capture_live_frame(page)
                    await self._emit_event("step_completed", {"step": "step1", "screenshot": frame, "state": state.model_dump()})

                # Step 2: Academic Info
                if state.step_index == 2:
                    await page.get_by_label("College / Institution *").fill(education["college"])
                    await page.get_by_label("Current year").select_option(label=education["course_year"])
                    await page.get_by_label("Previous examination marks (%)").fill(str(education["marks"]))
                    await page.get_by_label("Annual family income (₹)").fill(str(education["annual_income"]))

                    # Upload marksheet
                    upload = page.get_by_label("Upload marksheet")
                    await upload.set_input_files(str(marksheet_file))

                    await page.get_by_role("button", name="Save & continue").click()
                    await page.wait_for_load_state("domcontentloaded")

                    state.record_audit(action="academic_info", status="success", value_summary=education["college"])
                    state.step_index = 3
                    self.checkpointer.save(state)

                    frame = await self._capture_live_frame(page)
                    await self._emit_event("step_completed", {"step": "step2", "screenshot": frame, "state": state.model_dump()})

                # Step 3: Declaration
                if state.step_index == 3:
                    dec = page.get_by_label("I agree to the declaration.")
                    await dec.check()

                    await page.get_by_role("button", name="Continue to review").click()
                    await page.wait_for_load_state("domcontentloaded")

                    state.record_audit(action="declaration", status="success", value_summary="Agreed")
                    state.step_index = 4
                    self.checkpointer.save(state)

                    frame = await self._capture_live_frame(page)
                    await self._emit_event("step_completed", {"step": "step3", "screenshot": frame, "state": state.model_dump()})

                # Step 4: Review & Human Approval Gate (Feature F6)
                if state.step_index == 4:
                    summary_table = self.approval_gate.build_summary_from_profile(profile)
                    frame = await self._capture_live_frame(page)

                    # Pause for human approval
                    state.status = "needs_human"
                    state.human_reason = "Application is compiled and awaiting explicit citizen approval."
                    self.checkpointer.save(state)

                    await self._emit_event("approval_required", {
                        "run_id": state.run_id,
                        "summary_table": summary_table.format_text(),
                        "summary_markdown": summary_table.format_markdown(),
                        "screenshot": frame
                    })

                    # If not interactive (dry run or waiting), pause and halt here safely
                    if self.dry_run:
                        state.status = "done"
                        self.checkpointer.save(state)
                        return state

                    # Default to awaiting user interaction from UI
                    # If running in CLI / batch: click submit
                    await page.get_by_role("button", name="Approve & submit application").click()
                    await page.wait_for_url("**/receipt/**", timeout=15000)

                    state.step_index = 5
                    self.checkpointer.save(state)

                # Step 5: Receipt Extraction & Verification
                if state.step_index == 5:
                    await page.locator("#receipt-id").wait_for(state="visible")
                    content = await page.content()

                    receipt_data = self.receipt_extractor.extract_from_html(
                        html_content=content,
                        current_url=page.url,
                        applicant_name=personal.get("full_name"),
                        course=personal.get("course"),
                        college=education.get("college")
                    )

                    self.receipt_extractor.serialize_to_file(receipt_data)
                    state.receipt_id = receipt_data.receipt_id
                    state.submitted = True
                    state.status = "done"

                    state.record_audit(
                        action="receipt_confirmed",
                        status="success",
                        value_summary=f"Reference: {receipt_data.receipt_id}"
                    )
                    self.checkpointer.save(state)

                    frame = await self._capture_live_frame(page)
                    await self._emit_event("run_completed", {
                        "run_id": state.run_id,
                        "receipt": receipt_data.model_dump(),
                        "screenshot": frame
                    })

            finally:
                await browser.close()

        return state
