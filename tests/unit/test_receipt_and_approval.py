import tempfile
import unittest
from pathlib import Path

from agent.receipt import ReceiptExtractor, ReceiptData, InvalidReceiptError, RECEIPT_ID_REGEX
from agent.approval import ApprovalGate, ReviewSummaryTable, ApprovalResult
from agent.states import RunState


class TestReceiptAndApproval(unittest.TestCase):

    def setUp(self):
        self.extractor = ReceiptExtractor()
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_receipt_regex_pattern_compliance(self):
        """Verify strict regex matching of scholarship receipt IDs (SCH-XXXXXXXX)."""
        valid_ids = ["SCH-12345678", "SCH-ABCDEF01", "SCH-99AABBCC"]
        invalid_ids = ["SCH-123", "SCH-GGGGGGGG", "RECEIPT-12345678", "sch-12345678", "SCH-123456789"]

        for vid in valid_ids:
            self.assertIsNotNone(RECEIPT_ID_REGEX.search(vid), f"Should match valid ID: {vid}")

        for iid in invalid_ids:
            self.assertIsNone(RECEIPT_ID_REGEX.search(iid), f"Should NOT match invalid ID: {iid}")

    def test_extract_receipt_from_html(self):
        """Verify deterministic extraction directly from DOM HTML without using an LLM."""
        html = """
        <html><body>
            <div class="receipt card">
                <h1>Application received</h1>
                <p>Your demo scholarship application has been recorded successfully.</p>
                <div class="receipt-number">
                    <small>APPLICATION REFERENCE NUMBER</small>
                    <strong id="receipt-id">SCH-EF30697C</strong>
                </div>
            </div>
        </body></html>
        """
        data = self.extractor.extract_from_html(
            html_content=html,
            current_url="http://127.0.0.1:5000/receipt/SCH-EF30697C",
            applicant_name="Aarav Sharma",
            course="B.Tech"
        )

        self.assertEqual(data.receipt_id, "SCH-EF30697C")
        self.assertEqual(data.confirmation_title, "Application received")
        self.assertEqual(data.applicant_name, "Aarav Sharma")
        self.assertEqual(data.course, "B.Tech")

    def test_reject_missing_or_fabricated_receipt(self):
        """Verify extraction raises InvalidReceiptError when no valid ID is present."""
        html = "<html><body><h1>Submission Successful!</h1><p>Reference: NONE</p></body></html>"
        with self.assertRaises(InvalidReceiptError):
            self.extractor.extract_from_html(html, current_url="http://127.0.0.1:5000/receipt/fail")

    def test_serialize_receipt_json(self):
        """Verify saving structured receipt to a JSON file."""
        receipt = ReceiptData(
            receipt_id="SCH-B7C49102",
            confirmation_title="Application received",
            receipt_url="http://127.0.0.1:5000/receipt/SCH-B7C49102",
            applicant_name="Aarav Sharma"
        )
        out_path = Path(self.temp_dir.name) / "receipt.json"
        self.extractor.serialize_to_file(receipt, output_path=out_path)

        self.assertTrue(out_path.exists())
        with open(out_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("SCH-B7C49102", content)
        self.assertIn("Aarav Sharma", content)

    def test_summary_table_formatting(self):
        """Verify generation and formatting of the pre-submit review summary table."""
        gate = ApprovalGate()
        profile = {
            "personal": {"full_name": "Aarav Sharma", "course": "B.Tech"},
            "education": {"college": "Demo Institute", "marks": "82.5"}
        }
        table = gate.build_summary_from_profile(profile)

        text_output = table.format_text()
        markdown_output = table.format_markdown()

        self.assertIn("Full Name", text_output)
        self.assertIn("Aarav Sharma", text_output)
        self.assertIn("B.Tech", text_output)
        self.assertIn("| **Full Name** | `Aarav Sharma` |", markdown_output)

    def test_approval_gate_dry_run_mode(self):
        """Verify dry-run mode halts before final submit click."""
        gate = ApprovalGate(dry_run=True)
        table = ReviewSummaryTable()
        state = RunState()

        res = gate.evaluate_gate(summary=table, explicit_approval=True, state=state)
        self.assertFalse(res.approved)
        self.assertEqual(res.status, "dry_run_halted")
        self.assertIn("Dry-run", res.reason)

    def test_approval_gate_cannot_be_bypassed(self):
        """Playbook requirement: Test that approval gate cannot be bypassed silently."""
        gate = ApprovalGate(dry_run=False)
        table = ReviewSummaryTable()
        state = RunState()

        # Without explicit approval, must halt and NOT approve
        res = gate.evaluate_gate(summary=table, explicit_approval=None, state=state)
        self.assertFalse(res.approved)
        self.assertEqual(res.status, "awaiting_approval")
        self.assertEqual(state.status, "needs_human")

    def test_approval_gate_explicit_rejection(self):
        """Verify explicit user rejection stops the submission."""
        gate = ApprovalGate(dry_run=False)
        table = ReviewSummaryTable()
        state = RunState()

        res = gate.evaluate_gate(summary=table, explicit_approval=False, state=state)
        self.assertFalse(res.approved)
        self.assertEqual(res.status, "rejected")

    def test_approval_gate_explicit_approval_success(self):
        """Verify explicit approval enables proceeding to final submission."""
        gate = ApprovalGate(dry_run=False)
        table = ReviewSummaryTable()
        state = RunState()

        res = gate.evaluate_gate(summary=table, explicit_approval=True, state=state)
        self.assertTrue(res.approved)
        self.assertEqual(res.status, "approved")


if __name__ == "__main__":
    unittest.main()
