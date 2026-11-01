import re
from typing import Optional, Literal, Dict, Any
from pydantic import BaseModel, Field

from .states import RunState

try:
    from playwright.async_api import Page
except ImportError:
    Page = Any  # type: ignore

ChallengeType = Literal["captcha", "otp", "captcha_and_otp", "unknown_gate"]


class HumanChallenge(BaseModel):
    """Represents a human verification requirement detected on the portal."""
    challenge_type: ChallengeType
    title: str
    message: str
    url: str
    has_captcha_input: bool = False
    has_otp_input: bool = False
    captcha_hint: Optional[str] = None
    otp_hint: Optional[str] = None


class HumanHandoffManager:
    """
    Implements Feature F5: Human-in-the-loop for CAPTCHA and OTP from Section 5 of the Playbook:
    1. Detects challenge screens using known DOM selectors and keywords.
    2. Switches RunState to 'needs_human' and alerts the user.
    3. Handles entering user-provided CAPTCHA / OTP values and resuming execution.
    4. Never attempts to illegally bypass CAPTCHA systems.
    """

    @staticmethod
    def detect_challenge(html_content: str, current_url: str) -> Optional[HumanChallenge]:
        """
        Inspects page HTML and URL to identify CAPTCHA or OTP gates.
        """
        content_lower = html_content.lower()

        is_gate_url = "/human-check" in current_url
        has_captcha = 'id="captcha"' in html_content or 'name="captcha"' in html_content
        has_otp = 'id="otp"' in html_content or 'name="otp"' in html_content

        if not (is_gate_url or has_captcha or has_otp):
            return None

        # Extract hints if present on the mock portal (e.g. DEMO-1234 / 123456)
        captcha_hint_match = re.search(r'<div class="captcha"[^>]*>(.*?)</div>', html_content, re.IGNORECASE)
        captcha_hint = captcha_hint_match.group(1).strip() if captcha_hint_match else None

        otp_hint_match = re.search(r'<small[^>]*>.*?(\d{6}).*?</small>', html_content, re.IGNORECASE)
        otp_hint = otp_hint_match.group(1).strip() if otp_hint_match else None

        if has_captcha and has_otp:
            c_type = "captcha_and_otp"
        elif has_captcha:
            c_type = "captcha"
        else:
            c_type = "otp"

        return HumanChallenge(
            challenge_type=c_type,
            title="Human Verification Required",
            message="The portal requires human verification (CAPTCHA / OTP). The agent has paused.",
            url=current_url,
            has_captcha_input=has_captcha,
            has_otp_input=has_otp,
            captcha_hint=captcha_hint,
            otp_hint=otp_hint
        )

    def trigger_pause(self, state: RunState, challenge: HumanChallenge, checkpointer=None) -> None:
        """
        Pauses the agent state machine and logs the handoff audit event.
        """
        state.status = "needs_human"
        state.human_reason = f"Paused for {challenge.challenge_type}: {challenge.message}"
        state.record_audit(
            action="human_handoff_pause",
            selector="#captcha, #otp",
            status="warning",
            value_summary=challenge.message
        )
        if checkpointer:
            checkpointer.save(state)

    async def complete_challenge_and_resume(
        self,
        page: Page,
        state: RunState,
        captcha_solution: Optional[str] = None,
        otp_code: Optional[str] = None,
        checkpointer=None
    ) -> bool:
        """
        Inputs human-provided answers into the form, submits to verify, and resumes agent flow.
        """
        try:
            if captcha_solution:
                await page.locator("#captcha").fill(captcha_solution)

            if otp_code:
                await page.locator("#otp").fill(otp_code)

            await page.get_by_role("button", name="Verify & resume").click()
            await page.wait_for_load_state("domcontentloaded")

            # Check if gate was successfully cleared
            if "/human-check" not in page.url:
                state.status = "running"
                state.human_reason = None
                state.record_audit(
                    action="human_handoff_resumed",
                    status="success",
                    value_summary="Human verification successfully completed; agent resumed."
                )
                if checkpointer:
                    checkpointer.save(state)
                return True
            else:
                state.record_audit(
                    action="human_handoff_failed",
                    status="failure",
                    value_summary="Provided CAPTCHA/OTP did not pass portal validation."
                )
                return False

        except Exception as e:
            state.record_audit(
                action="human_handoff_error",
                status="failure",
                error_message=str(e)
            )
            return False
