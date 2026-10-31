import unittest
from agent.verifier import PageVerifier, VerificationResult


class TestPageVerifier(unittest.TestCase):

    def test_verify_success_page(self):
        """Verify normal page state matching expected URL and heading."""
        url = "http://127.0.0.1:5000/application/1"
        html = """
        <html><body>
            <header>Demo</header>
            <main>
                <h1>Applicant information</h1>
                <form><input id="name"></form>
            </main>
        </body></html>
        """
        res = PageVerifier.classify_html(
            url=url,
            html_content=html,
            expected_url_pattern=r"/application/1",
            expected_heading="Applicant information"
        )
        self.assertTrue(res.success)
        self.assertEqual(res.issue_type, "none")
        self.assertEqual(res.heading, "Applicant information")

    def test_detect_server_error_500(self):
        """Verify detection of simulated 500 error page (?flaky_500=1)."""
        url = "http://127.0.0.1:5000/application/1?flaky_500=1"
        html = """
        <html><body>
            <div class="card form-card">
                <div class="eyebrow">PORTAL ERROR</div>
                <h1>Temporary server error (demo scenario).</h1>
                <p class="muted">Reload with fail_once=0 to continue the demo.</p>
            </div>
        </body></html>
        """
        res = PageVerifier.classify_html(url=url, html_content=html)
        self.assertFalse(res.success)
        self.assertEqual(res.issue_type, "server_error_500")
        self.assertIn("server error", res.message.lower())

    def test_detect_human_gate_captcha_otp(self):
        """Verify detection of human security gate (?gate=1)."""
        url = "http://127.0.0.1:5000/human-check?gate=1"
        html = """
        <html><body>
            <h1>Human verification required</h1>
            <input id="captcha" name="captcha">
            <input id="otp" name="otp">
        </body></html>
        """
        res = PageVerifier.classify_html(url=url, html_content=html)
        self.assertFalse(res.success)
        self.assertEqual(res.issue_type, "human_gate")
        self.assertIn("human", res.message.lower())

    def test_detect_session_expired(self):
        """Verify detection of unexpected session expiry redirect (?expire_session=1)."""
        # Agent expected to be on application step 2, but portal kicked back to /login
        url = "http://127.0.0.1:5000/login?expire_session=1"
        html = """
        <html><body>
            <h1>Apply for a scholarship</h1>
            <h2>Applicant Login</h2>
            <form><input id="username"></form>
        </body></html>
        """
        res = PageVerifier.classify_html(
            url=url,
            html_content=html,
            expected_url_pattern=r"/application/2",
            expected_heading="Academic information"
        )
        self.assertFalse(res.success)
        self.assertEqual(res.issue_type, "session_expired")
        self.assertIn("session expired", res.message.lower())

    def test_detect_popup_banner(self):
        """Verify detection of dismissible modal / announcement (?popup=1)."""
        url = "http://127.0.0.1:5000/application/1?popup=1"
        html = """
        <html><body>
            <div class="alert warning" data-dismiss>
                Notice: Your profile session is active. <button type="button" data-dismiss>Dismiss ×</button>
            </div>
            <h1>Applicant information</h1>
        </body></html>
        """
        res = PageVerifier.classify_html(url=url, html_content=html)
        self.assertFalse(res.success)
        self.assertEqual(res.issue_type, "popup_or_modal")
        self.assertEqual(res.popup_selector, "button[data-dismiss], [data-dismiss]")
        self.assertIn("Notice:", res.alert_text)

    def test_detect_validation_error(self):
        """Verify detection of form flash validation errors."""
        url = "http://127.0.0.1:5000/application/1"
        html = """
        <html><body>
            <div class="alert error">Please complete the required personal details.</div>
            <h1>Applicant information</h1>
        </body></html>
        """
        res = PageVerifier.classify_html(url=url, html_content=html)
        self.assertFalse(res.success)
        self.assertEqual(res.issue_type, "validation_error")
        self.assertIn("Please complete the required personal details.", res.alert_text)

    def test_detect_url_mismatch(self):
        """Verify detection when browser failed to advance to the next step."""
        url = "http://127.0.0.1:5000/review"
        html = "<html><body><h1>Review your application</h1></body></html>"

        res = PageVerifier.classify_html(
            url=url,
            html_content=html,
            expected_url_pattern=r"/receipt/[A-Z0-9-]+"
        )
        self.assertFalse(res.success)
        self.assertEqual(res.issue_type, "url_mismatch")

    def test_detect_missing_heading(self):
        """Verify detection when expected page heading is not displayed."""
        url = "http://127.0.0.1:5000/application/1"
        html = "<html><body><h1>Unexpected Heading</h1></body></html>"

        res = PageVerifier.classify_html(
            url=url,
            html_content=html,
            expected_heading="Applicant information"
        )
        self.assertFalse(res.success)
        self.assertEqual(res.issue_type, "missing_heading")


if __name__ == "__main__":
    unittest.main()
