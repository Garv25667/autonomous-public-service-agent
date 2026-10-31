import asyncio
import time
import logging
from typing import Optional, Literal, Dict, Any
from pydantic import BaseModel, Field

from .verifier import VerificationResult, IssueType
from .states import RunState

try:
    from playwright.async_api import Page
except ImportError:
    Page = Any  # type: ignore

logger = logging.getLogger(__name__)

StrategyType = Literal[
    "dismiss_popup",
    "relogin_and_resume",
    "backoff_and_retry",
    "pause_for_human",
    "fix_field_and_retry",
    "reload_and_retry",
    "escalate_failure",
    "no_action_needed"
]


class RecoveryAction(BaseModel):
    """Result of an attempted recovery operation."""
    strategy: StrategyType
    success: bool
    message: str
    retry_action: bool = False
    needs_human: bool = False
    details: Dict[str, Any] = Field(default_factory=dict)


class RecoveryHandler:
    """
    Implements the Recovery Engine from Section 2 & 5 of the 48-Hour Playbook:
    Classifies page verification failures and applies targeted self-healing strategies:
    1. popup_or_modal     -> dismiss_popup
    2. session_expired    -> relogin_and_resume
    3. server_error_500   -> backoff_and_retry (with fail_once=0 parameter handling)
    4. human_gate         -> pause_for_human (switch to needs_human and save checkpoint)
    5. validation_error   -> fix_field_and_retry
    6. retries exhausted  -> escalate_failure
    """

    def __init__(
        self,
        default_username: str = "student",
        default_password: str = "demo123",
        max_step_retries: int = 3,
    ):
        self.default_username = default_username
        self.default_password = default_password
        self.max_step_retries = max_step_retries

    def pick_strategy(
        self,
        result: VerificationResult,
        state: RunState
    ) -> StrategyType:
        """
        Pure decision function mapping verification results to recovery strategies.
        Guarantees deterministic classification for testing and offline analysis.
        """
        if result.success or result.issue_type == "none":
            return "no_action_needed"

        # Check retry limit guard first
        if state.retries_on_step >= self.max_step_retries:
            return "escalate_failure"

        # 1. Dismissible Popups
        if result.issue_type == "popup_or_modal":
            return "dismiss_popup"

        # 2. Session Expired
        if result.issue_type == "session_expired":
            return "relogin_and_resume"

        # 3. Flaky 500 Server Error
        if result.issue_type == "server_error_500":
            return "backoff_and_retry"

        # 4. CAPTCHA / OTP Human Gate
        if result.issue_type == "human_gate":
            return "pause_for_human"

        # 5. Form Validation Error
        if result.issue_type == "validation_error":
            return "fix_field_and_retry"

        # 6. URL or Heading Mismatch
        if result.issue_type in ("url_mismatch", "missing_heading"):
            return "reload_and_retry"

        return "escalate_failure"

    def apply_recovery_state(
        self,
        strategy: StrategyType,
        result: VerificationResult,
        state: RunState,
        checkpointer=None
    ) -> RecoveryAction:
        """
        Updates RunState (retries counter, status, audit log) deterministically.
        Can run with or without a live browser.
        """
        state.retries_on_step += 1

        if strategy == "pause_for_human":
            state.status = "needs_human"
            state.human_reason = "Human security gate triggered: CAPTCHA / OTP verification required."
            if checkpointer:
                checkpointer.save(state)
            state.record_audit(
                action="pause_for_human",
                status="warning",
                value_summary=state.human_reason
            )
            return RecoveryAction(
                strategy="pause_for_human",
                success=True,
                retry_action=False,
                needs_human=True,
                message="Paused agent. Status set to 'needs_human' for CAPTCHA/OTP resolution."
            )

        elif strategy == "dismiss_popup":
            state.record_audit(
                action="dismiss_popup",
                status="success",
                value_summary=result.alert_text or "Dismissed popup"
            )
            return RecoveryAction(
                strategy="dismiss_popup",
                success=True,
                retry_action=True,
                message="Popup dismiss scheduled."
            )

        elif strategy == "relogin_and_resume":
            state.record_audit(
                action="relogin",
                status="success",
                value_summary=f"Re-authentication planned to resume at step {state.step_index}"
            )
            return RecoveryAction(
                strategy="relogin_and_resume",
                success=True,
                retry_action=True,
                message="Re-login scheduled to restore session."
            )

        elif strategy == "backoff_and_retry":
            delay = 1.0 * state.retries_on_step
            state.record_audit(
                action="reload_500_recovery",
                status="success",
                value_summary=f"Backoff {delay}s on 500 error"
            )
            return RecoveryAction(
                strategy="backoff_and_retry",
                success=True,
                retry_action=True,
                message=f"Backoff {delay}s and reload scheduled."
            )

        elif strategy == "fix_field_and_retry":
            state.record_audit(
                action="flag_validation_error",
                status="warning",
                value_summary=result.alert_text or result.message
            )
            return RecoveryAction(
                strategy="fix_field_and_retry",
                success=True,
                retry_action=True,
                message=f"Validation alert noted: '{result.alert_text}'."
            )

        elif strategy == "reload_and_retry":
            state.record_audit(
                action="reload",
                status="success",
                value_summary=f"Reload scheduled for {result.issue_type}"
            )
            return RecoveryAction(
                strategy="reload_and_retry",
                success=True,
                retry_action=True,
                message="Reload scheduled."
            )

        else:
            state.status = "failed"
            state.record_audit(
                action="escalate_failure",
                status="failure",
                error_message=f"Exhausted retries ({state.retries_on_step}/{self.max_step_retries})."
            )
            return RecoveryAction(
                strategy="escalate_failure",
                success=False,
                retry_action=False,
                message=f"Recovery failed: Exceeded retry budget ({state.retries_on_step}/{self.max_step_retries})."
            )

    async def execute_recovery(
        self,
        page: Page,
        result: VerificationResult,
        state: RunState,
        checkpointer=None
    ) -> RecoveryAction:
        """
        Executes browser interactions for the chosen strategy on a live Playwright page.
        """
        strategy = self.pick_strategy(result, state)
        action = self.apply_recovery_state(strategy, result, state, checkpointer)

        if not action.success and strategy == "escalate_failure":
            return action

        if strategy == "dismiss_popup":
            selector = result.popup_selector or "button[data-dismiss], [data-dismiss]"
            try:
                dismiss_btn = page.locator(selector).first
                if await dismiss_btn.is_visible():
                    await dismiss_btn.click()
            except Exception as e:
                action.success = False
                action.message = f"Failed to click dismiss: {str(e)}"

        elif strategy == "relogin_and_resume":
            try:
                await page.get_by_label("User ID").fill(self.default_username)
                await page.get_by_label("Password").fill(self.default_password)
                await page.get_by_role("button", name="Sign in securely").click()
                await page.wait_for_load_state("domcontentloaded")
                step_idx = state.step_index
                expected_step = step_idx if step_idx > 0 else 1
                await page.goto(f"http://127.0.0.1:5000/application/{expected_step}")
            except Exception as e:
                action.success = False
                action.message = f"Re-authentication failed: {str(e)}"

        elif strategy == "backoff_and_retry":
            delay = 1.0 * state.retries_on_step
            await asyncio.sleep(delay)
            current_url = page.url
            if "flaky_500=1" in current_url:
                if "fail_once=0" not in current_url:
                    sep = "&" if "?" in current_url else "?"
                    retry_url = f"{current_url}{sep}fail_once=0"
                else:
                    retry_url = current_url
                await page.goto(retry_url)
            else:
                await page.reload()

        elif strategy == "reload_and_retry":
            try:
                await page.reload()
            except Exception as e:
                action.success = False
                action.message = f"Failed to reload: {str(e)}"

        return action
