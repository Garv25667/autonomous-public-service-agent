import json
import tempfile
import unittest
from pathlib import Path

from agent.eligibility import EligibilityEvaluator, EligibilityResult
from agent.tools.docs import DocumentProcessor, DocumentValidationResult
from agent.handoff import HumanHandoffManager, HumanChallenge
from agent.states import RunState


class TestStep8(unittest.TestCase):

    def setUp(self):
        self.root = Path(__file__).resolve().parents[2]
        self.rules_path = self.root / "rules" / "scholarship.yaml"
        self.evaluator = EligibilityEvaluator(rules_path=self.rules_path)
        self.doc_processor = DocumentProcessor(max_size_mb=2.0)
        self.handoff_manager = HumanHandoffManager()

        # Load standard synthetic profile
        with open(self.root / "data" / "citizen.json", "r", encoding="utf-8") as f:
            self.citizen_data = json.load(f)

    # -------------------------------------------------------------
    # Feature F3: Eligibility Evaluation Tests
    # -------------------------------------------------------------
    def test_eligibility_standard_profile_satisfies_all_rules(self):
        """Verify the standard synthetic citizen profile satisfies all scholarship rules."""
        result = self.evaluator.evaluate(self.citizen_data)
        self.assertTrue(result.eligible)
        self.assertEqual(len(result.missing_docs), 0)
        self.assertIn("All criteria satisfied", result.friendly_explanation)

    def test_eligibility_rejects_exceeded_income(self):
        """Verify income above ceiling flags ineligible."""
        profile = json.loads(json.dumps(self.citizen_data))
        profile["education"]["annual_income"] = "950000"  # Exceeds ₹8,00,000

        result = self.evaluator.evaluate(profile)
        self.assertFalse(result.eligible)
        self.assertTrue(any("exceeds ceiling" in r for r in result.reasons))

    def test_eligibility_rejects_low_marks(self):
        """Verify marks below 60% flags ineligible."""
        profile = json.loads(json.dumps(self.citizen_data))
        profile["education"]["marks"] = "54.0"  # Below 60%

        result = self.evaluator.evaluate(profile)
        self.assertFalse(result.eligible)
        self.assertTrue(any("below minimum requirement" in r for r in result.reasons))

    def test_eligibility_flags_missing_document_file(self):
        """Verify missing marksheet file on disk is flagged as missing doc."""
        profile = json.loads(json.dumps(self.citizen_data))
        profile["education"]["marksheet_path"] = "data/non_existent_file.pdf"

        result = self.evaluator.evaluate(profile)
        self.assertFalse(result.eligible)
        self.assertIn("marksheet", result.missing_docs)

    # -------------------------------------------------------------
    # Feature F4: Document Readiness Tests
    # -------------------------------------------------------------
    def test_document_processor_validates_demo_marksheet(self):
        """Verify demo_marksheet.pdf passes format, size, and page count checks."""
        marksheet_path = self.root / "data" / "demo_marksheet.pdf"
        result = self.doc_processor.validate_file(marksheet_path)

        self.assertTrue(result.valid)
        self.assertLess(result.file_size_mb, 2.0)
        self.assertGreaterEqual(result.page_count, 1)

    def test_document_processor_rejects_oversized_file(self):
        """Verify files over 2 MB are rejected before opening the browser."""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
            # Write 2.5 MB of dummy data
            tf.write(b"0" * int(2.5 * 1024 * 1024))
            temp_path = Path(tf.name)

        try:
            result = self.doc_processor.validate_file(temp_path)
            self.assertFalse(result.valid)
            self.assertIn("exceeds portal limit", result.error_message)
        finally:
            temp_path.unlink(missing_ok=True)

    def test_document_processor_rejects_unsupported_format(self):
        """Verify non-standard formats (e.g. .exe, .txt) are rejected."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tf:
            tf.write(b"text file")
            temp_path = Path(tf.name)

        try:
            result = self.doc_processor.validate_file(temp_path)
            self.assertFalse(result.valid)
            self.assertIn("Unsupported format", result.error_message)
        finally:
            temp_path.unlink(missing_ok=True)

    # -------------------------------------------------------------
    # Feature F5: Human-in-the-Loop Handoff Tests
    # -------------------------------------------------------------
    def test_detect_human_challenge_on_gate_html(self):
        """Verify detection of CAPTCHA + OTP challenge screen."""
        gate_html = """
        <html><body>
            <div class="page-heading"><h1>Human verification required</h1></div>
            <form>
                <input id="captcha" name="captcha">
                <div class="captcha">DEMO-1234</div>
                <input id="otp" name="otp">
                <small>Demo OTP: 123456</small>
            </form>
        </body></html>
        """
        challenge = self.handoff_manager.detect_challenge(
            html_content=gate_html,
            current_url="http://127.0.0.1:5000/human-check?gate=1"
        )

        self.assertIsNotNone(challenge)
        self.assertEqual(challenge.challenge_type, "captcha_and_otp")
        self.assertEqual(challenge.captcha_hint, "DEMO-1234")
        self.assertEqual(challenge.otp_hint, "123456")

    def test_detect_human_challenge_none_on_regular_page(self):
        """Verify returns None when on a regular portal page."""
        normal_html = "<html><body><h1>Applicant information</h1></body></html>"
        challenge = self.handoff_manager.detect_challenge(
            html_content=normal_html,
            current_url="http://127.0.0.1:5000/application/1"
        )
        self.assertIsNone(challenge)

    def test_trigger_pause_sets_state_needs_human(self):
        """Verify triggering handoff pauses RunState with needs_human status."""
        challenge = HumanChallenge(
            challenge_type="captcha_and_otp",
            title="Verification Required",
            message="Please enter OTP",
            url="http://127.0.0.1:5000/human-check"
        )
        state = RunState(run_id="run_pause_test")
        self.assertEqual(state.status, "running")

        self.handoff_manager.trigger_pause(state, challenge)
        self.assertEqual(state.status, "needs_human")
        self.assertIn("captcha_and_otp", state.human_reason)
        self.assertEqual(len(state.audit), 1)
        self.assertEqual(state.audit[0].action, "human_handoff_pause")


if __name__ == "__main__":
    unittest.main()
