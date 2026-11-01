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
from .handoff import HumanHandoffManager, HumanChallenge
from .tools.secrets import SecretVault
from .tools.docs import DocumentProcessor
from .eligibility import EligibilityEvaluator, EligibilityResult
from .approval import ApprovalGate, ReviewSummaryTable
from .receipt import ReceiptExtractor, ReceiptData
from .workflow_cache import WorkflowCache, CachedStep

ROOT = Path(__file__).resolve().parents[1]


class AgentOrchestrator:
    """
    Main state machine orchestrating the full autonomous public service pipeline:
    INTAKE -> ELIGIBILITY -> PLAN -> [ OBSERVE -> DECIDE -> ACT -> VERIFY ]* -> APPROVAL -> SUBMIT -> RECEIPT
    """

    def __init__(
        self,
        portal_base_url: str = "http://127.0.0.1:5000",
        query_params: str = "",
        headless: bool = False,
        dry_run: bool = False,
        auto_approve: bool = False,
        auto_solve_gate: bool = False,
        broadcast_callback: Optional[Callable[[Dict[str, Any]], Any]] = None
    ):
        self.portal_base_url = portal_base_url.rstrip("/")
        if query_params and not query_params.startswith("?"):
            query_params = "?" + query_params
        self.query_params = query_params
        self.headless = headless
        self.dry_run = dry_run
        self.auto_approve = auto_approve
        self.auto_solve_gate = auto_solve_gate
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
        self.handoff = HumanHandoffManager()
        self.approval_gate = ApprovalGate(dry_run=dry_run)
        self.receipt_extractor = ReceiptExtractor()
        self.workflow_cache = WorkflowCache()

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
                    login_url = f"{self.portal_base_url}/login{self.query_params}"
                    await page.goto(login_url)
                    await page.wait_for_load_state("domcontentloaded")

                    # Check for 500 error on load (flaky_500 scenario)
                    content = await page.content()
                    verification = self.verifier.classify_html(page.url, content)
                    if not verification.success and verification.issue_type == "server_error_500":
                        rec_action = await self.recovery.execute_recovery(page, verification, state, self.checkpointer)
                        if rec_action.retry_action:
                            await page.wait_for_load_state("domcontentloaded")

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
                    # Check for popup overlay (popup scenario)
                    content = await page.content()
                    ver = self.verifier.classify_html(page.url, content)
                    if ver.issue_type == "popup_or_modal":
                        await self.recovery.execute_recovery(page, ver, state, self.checkpointer)
                        await page.wait_for_load_state("domcontentloaded")

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

                    # Cascading dropdowns (State -> District -> Block)
                    await page.get_by_label("State").select_option(label=personal["state"])
                    await asyncio.sleep(0.15)
                    await page.get_by_label("District").select_option(label=personal["district"])
                    await asyncio.sleep(0.15)
                    await page.get_by_label("Block / Taluka").select_option(label=personal["block"])

                    await page.get_by_role("button", name="Save & continue").click()
                    await page.wait_for_load_state("domcontentloaded")

                    # Verify step 1 -> step 2 transition (e.g. check for session expiry)
                    verification = await self.verifier.verify_page(page, expected_heading="Academic information")
                    if not verification.success:
                        action = await self.recovery.execute_recovery(page, verification, state, self.checkpointer)
                        if action.needs_human:
                            return state
                        if action.retry_action:
                            await page.wait_for_load_state("domcontentloaded")

                    state.record_audit(action="personal_info", status="success", value_summary=personal["full_name"])
                    state.step_index = 2
                    self.checkpointer.save(state)

                    # Record successful Step 1 workflow into replay cache
                    fp1 = self.workflow_cache.compute_page_fingerprint("/application/1", ["Full name *", "Date of birth *", "Category", "Current course", "State", "District", "Block / Taluka"])
                    self.workflow_cache.record_step(fp1, "/application/1", CachedStep(step_id="full_name", intent="fill_name", action_type="fill", locator_strategy="label", locator_target="Full name *", value_ref="personal.full_name"))
                    self.workflow_cache.record_step(fp1, "/application/1", CachedStep(step_id="category", intent="select_cat", action_type="select", locator_strategy="label", locator_target="Category", value_ref="personal.category"))

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

                    verification = await self.verifier.verify_page(page, expected_heading="Declaration")
                    if not verification.success:
                        action = await self.recovery.execute_recovery(page, verification, state, self.checkpointer)
                        if action.needs_human:
                            return state
                        if action.retry_action:
                            await page.wait_for_load_state("domcontentloaded")

                    state.record_audit(action="academic_info", status="success", value_summary=education["college"])
                    state.step_index = 3
                    self.checkpointer.save(state)

                    frame = await self._capture_live_frame(page)
                    await self._emit_event("step_completed", {"step": "step2", "screenshot": frame, "state": state.model_dump()})

                # Step 3: Declaration & Gate Check
                if state.step_index == 3:
                    dec = page.get_by_label("I agree to the declaration.")
                    await dec.check()

                    await page.get_by_role("button", name="Continue to review").click()
                    await page.wait_for_load_state("domcontentloaded")

                    # Check for human verification gate (e.g. gate=1)
                    if "/human-check" in page.url:
                        challenge = self.handoff.detect_challenge(await page.content(), page.url)
                        if challenge:
                            self.handoff.trigger_pause(state, challenge, self.checkpointer)
                            frame = await self._capture_live_frame(page)
                            await self._emit_event("human_gate_required", {
                                "run_id": state.run_id,
                                "challenge": challenge.model_dump(),
                                "screenshot": frame
                            })
                            if self.auto_solve_gate:
                                solved = await self.handoff.complete_challenge_and_resume(
                                    page, state,
                                    captcha_solution="DEMO-1234",
                                    otp_code="123456",
                                    checkpointer=self.checkpointer
                                )
                                if not solved:
                                    return state
                                await page.wait_for_load_state("domcontentloaded")
                            else:
                                return state

                    state.record_audit(action="declaration", status="success", value_summary="Agreed")
                    state.step_index = 4
                    self.checkpointer.save(state)

                    frame = await self._capture_live_frame(page)
                    await self._emit_event("step_completed", {"step": "step3", "screenshot": frame, "state": state.model_dump()})

                # Step 4: Review & Human Approval Gate (Feature F6)
                if state.step_index == 4:
                    summary_table = self.approval_gate.build_summary_from_profile(profile)
                    frame = await self._capture_live_frame(page)

                    # If dry run mode, stop before final submission
                    if self.dry_run:
                        state.status = "done"
                        state.record_audit(action="dry_run_halt", status="success", value_summary="Pre-submission halt")
                        self.checkpointer.save(state)
                        return state

                    # Check explicit human approval
                    if not self.auto_approve:
                        state.status = "needs_human"
                        state.human_reason = "Application is compiled and awaiting explicit citizen approval."
                        self.checkpointer.save(state)

                        await self._emit_event("approval_required", {
                            "run_id": state.run_id,
                            "summary_table": summary_table.format_text(),
                            "summary_markdown": summary_table.format_markdown(),
                            "screenshot": frame
                        })
                        return state

                    # User has approved or auto_approve is granted
                    approval_res = self.approval_gate.request_approval(summary_table, explicit_approval=True)
                    state.record_audit(action="approval_granted", status="success", value_summary="Explicit citizen approval")

                    await page.get_by_role("button", name="Approve & submit application").click()
                    await page.wait_for_url("**/receipt/**", timeout=15000)

                    state.step_index = 5
                    self.checkpointer.save(state)

                # Step 5: Receipt Extraction & Verification
                if state.step_index == 5:
                    await page.locator("#receipt-id").wait_for(state="visible", timeout=15000)
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
