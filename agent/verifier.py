import re
from typing import Optional, Literal, Dict, Any
from pydantic import BaseModel, Field

try:
    from playwright.async_api import Page
except ImportError:
    Page = Any  # type: ignore

IssueType = Literal[
    "none",
    "validation_error",     # Form flash alert (e.g. "Please complete the required details", "File too large")
    "popup_or_modal",       # Notice with data-dismiss or alert warning
    "session_expired",      # Unexpected redirect to /login or session cleared
    "server_error_500",     # 500 error page with eyebrow 'PORTAL ERROR'
    "human_gate",           # CAPTCHA / OTP screen at /human-check
    "url_mismatch",         # URL does not match expected pattern
    "missing_heading",      # Expected h1/h2 heading missing
    "field_mismatch",       # Input field does not contain expected value
    "unknown_error"
]


class VerificationResult(BaseModel):
    """Structured diagnosis emitted by the Verifier after every browser action."""
    success: bool
    issue_type: IssueType = "none"
    message: str = ""
    current_url: str = ""
    heading: Optional[str] = None
    alert_text: Optional[str] = None
    popup_selector: Optional[str] = None
    field_name: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class PageVerifier:
    """
    Implements deterministic verification checks outlined in Section 2 of the 48-Hour Playbook:
    1. Server error (500) detection
    2. Human gate (CAPTCHA/OTP) detection
    3. Session expiration detection
    4. Popup / modal announcement detection
    5. Form validation error banner detection
    6. Expected URL pattern matching
    7. Expected heading verification
    8. Form field value read-back
    """

    @staticmethod
    def classify_html(
        url: str,
        html_content: str,
        expected_url_pattern: Optional[str] = None,
        expected_heading: Optional[str] = None,
    ) -> VerificationResult:
        """
        Pure deterministic classifier that analyzes URL and HTML snapshots.
        Enables lightning-fast component testing without launching Chromium.
        """
        content_lower = html_content.lower()

        # 1. Check for Server Error (500)
        if "portal error" in content_lower or "temporary server error" in content_lower or "500 internal server error" in content_lower:
            return VerificationResult(
                success=False,
                issue_type="server_error_500",
                message="Portal server error detected (500 error page).",
                current_url=url
            )

        # 2. Check for Human Gate (CAPTCHA / OTP at /human-check)
        if "/human-check" in url or "human verification required" in content_lower or 'name="captcha"' in content_lower:
            return VerificationResult(
                success=False,
                issue_type="human_gate",
                message="Human verification gate detected (CAPTCHA/OTP required).",
                current_url=url
            )

        # 3. Check for Session Expiration (redirected to /login unexpectedly)
        is_at_login = "/login" in url.split("?")[0]
        expected_is_login = expected_url_pattern and "/login" in expected_url_pattern
        if is_at_login and not expected_is_login:
            return VerificationResult(
                success=False,
                issue_type="session_expired",
                message="Session expired; unexpectedly redirected to login page.",
                current_url=url
            )

        # 4. Check for Popups / Dismissible Modals (data-dismiss)
        if "data-dismiss" in html_content:
            # Extract alert message if available
            alert_match = re.search(r'class="alert warning"[^>]*>(.*?)</div>', html_content, re.DOTALL | re.IGNORECASE)
            alert_txt = alert_match.group(1).strip() if alert_match else "Dismissible notice overlay present"
            # Strip tags from alert text
            clean_txt = re.sub(r'<[^>]+>', ' ', alert_txt).strip()
            return VerificationResult(
                success=False,
                issue_type="popup_or_modal",
                message="Dismissible popup or banner is blocking the page.",
                alert_text=clean_txt,
                popup_selector="button[data-dismiss], [data-dismiss]",
                current_url=url
            )

        # 5. Check for Form Validation Error Banners (.alert.error)
        if 'class="alert error"' in html_content:
            error_match = re.search(r'class="alert error"[^>]*>(.*?)</div>', html_content, re.DOTALL | re.IGNORECASE)
            err_txt = error_match.group(1).strip() if error_match else "Form validation error"
            clean_err = re.sub(r'<[^>]+>', ' ', err_txt).strip()
            return VerificationResult(
                success=False,
                issue_type="validation_error",
                message=f"Validation error banner: {clean_err}",
                alert_text=clean_err,
                current_url=url
            )

        # 6. Check Expected URL pattern
        if expected_url_pattern:
            if not re.search(expected_url_pattern, url):
                return VerificationResult(
                    success=False,
                    issue_type="url_mismatch",
                    message=f"URL mismatch: expected pattern '{expected_url_pattern}', got '{url}'",
                    current_url=url
                )

        # 7. Check Expected Heading
        extracted_heading = None
        h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', html_content, re.DOTALL | re.IGNORECASE)
        if h1_match:
            extracted_heading = re.sub(r'<[^>]+>', '', h1_match.group(1)).strip()

        if expected_heading:
            if not extracted_heading or expected_heading.lower() not in extracted_heading.lower():
                return VerificationResult(
                    success=False,
                    issue_type="missing_heading",
                    message=f"Expected heading '{expected_heading}' not found. Current: '{extracted_heading}'",
                    current_url=url,
                    heading=extracted_heading
                )

        # All checks passed
        return VerificationResult(
            success=True,
            issue_type="none",
            message="Page verification succeeded.",
            current_url=url,
            heading=extracted_heading
        )

    @classmethod
    async def verify_page(
        cls,
        page: Page,
        expected_url_pattern: Optional[str] = None,
        expected_heading: Optional[str] = None
    ) -> VerificationResult:
        """
        Inspects an active Playwright page in real-time.
        Performs live DOM queries before falling back to snapshot classification.
        """
        current_url = page.url
        content = await page.content()

        # Run pure classifier
        result = cls.classify_html(
            url=current_url,
            html_content=content,
            expected_url_pattern=expected_url_pattern,
            expected_heading=expected_heading
        )

        return result

    @classmethod
    async def verify_field(
        cls,
        page: Page,
        selector_or_label: str,
        expected_value: str
    ) -> VerificationResult:
        """
        Reads back an input or select field's value to confirm it equals what was typed.
        """
        current_url = page.url
        try:
            # Try by label first, then by selector
            try:
                locator = page.get_by_label(selector_or_label)
                actual_val = await locator.input_value()
            except Exception:
                locator = page.locator(selector_or_label)
                actual_val = await locator.input_value()

            if actual_val.strip() == expected_value.strip():
                return VerificationResult(
                    success=True,
                    issue_type="none",
                    message=f"Field '{selector_or_label}' confirmed: '{actual_val}'",
                    current_url=current_url,
                    field_name=selector_or_label
                )
            else:
                return VerificationResult(
                    success=False,
                    issue_type="field_mismatch",
                    message=f"Field value mismatch on '{selector_or_label}': expected '{expected_value}', got '{actual_val}'",
                    current_url=current_url,
                    field_name=selector_or_label,
                    details={"expected": expected_value, "actual": actual_val}
                )
        except Exception as e:
            return VerificationResult(
                success=False,
                issue_type="unknown_error",
                message=f"Could not read field '{selector_or_label}': {str(e)}",
                current_url=current_url,
                field_name=selector_or_label
            )
