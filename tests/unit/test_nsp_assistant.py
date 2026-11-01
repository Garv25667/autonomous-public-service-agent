import unittest
import tempfile
import json
import yaml
from pathlib import Path

from agent.nsp_assistant import NSPAssistant, NSPValidationSummary

ROOT = Path(__file__).resolve().parents[2]


class TestNSPAssistant(unittest.TestCase):
    def setUp(self):
        self.assistant = NSPAssistant()

    def test_load_nsp_rules(self):
        rules = self.assistant.rules
        self.assertIn("rules", rules)
        self.assertEqual(rules["rules"]["income_ceiling"], 450000.0)
        self.assertEqual(rules["rules"]["min_marks_percentage"], 75.0)

    def test_check_nsp_eligibility_default_profile(self):
        res = self.assistant.check_nsp_eligibility()
        self.assertTrue(res.eligible)
        self.assertIn("Central Sector Scheme", res.friendly_explanation)

    def test_check_nsp_eligibility_high_income(self):
        temp_dir = tempfile.TemporaryDirectory()
        profile_path = Path(temp_dir.name) / "test_citizen.json"
        
        profile = dict(self.assistant.profile)
        profile["education"] = dict(profile["education"])
        profile["education"]["annual_income"] = "600000"  # Exceeds 450,000
        
        with open(profile_path, "w", encoding="utf-8") as f:
            json.dump(profile, f)

        custom_assistant = NSPAssistant(profile_path=profile_path)
        res = custom_assistant.check_nsp_eligibility()
        self.assertFalse(res.eligible)
        self.assertTrue(any("exceeds NSP limit" in r for r in res.reasons))
        temp_dir.cleanup()

    def test_check_nsp_eligibility_low_marks(self):
        temp_dir = tempfile.TemporaryDirectory()
        profile_path = Path(temp_dir.name) / "test_citizen.json"
        
        profile = dict(self.assistant.profile)
        profile["education"] = dict(profile["education"])
        profile["education"]["marks"] = "70.0"  # Below 75%
        
        with open(profile_path, "w", encoding="utf-8") as f:
            json.dump(profile, f)

        custom_assistant = NSPAssistant(profile_path=profile_path)
        res = custom_assistant.check_nsp_eligibility()
        self.assertFalse(res.eligible)
        self.assertTrue(any("below NSP requirement" in r for r in res.reasons))
        temp_dir.cleanup()

    def test_validate_nsp_document_under_200kb(self):
        valid, size_kb, msg = self.assistant.validate_nsp_document()
        self.assertTrue(valid)
        self.assertLessEqual(size_kb, 200.0)

    def test_run_preflight_audit(self):
        audit = self.assistant.run_preflight_audit()
        self.assertIsInstance(audit, NSPValidationSummary)
        self.assertTrue(audit.eligible)
        self.assertTrue(audit.document_valid)
        self.assertIn("personal", audit.sanitized_profile)


if __name__ == "__main__":
    unittest.main()
