import json
import unittest
from pathlib import Path

from agent.tools.secrets import SecretVault, PIILeakDetectedError


class TestSecretsAndPII(unittest.TestCase):

    def setUp(self):
        self.vault = SecretVault()
        self.root = Path(__file__).resolve().parents[2]
        citizen_path = self.root / "data" / "citizen.json"
        with open(citizen_path, "r", encoding="utf-8") as f:
            self.citizen_data = json.load(f)

    def test_vault_placeholder_registration(self):
        """Verify registering a secret creates a valid placeholder."""
        token = self.vault.register_secret("full_name", "Aarav Sharma")
        self.assertEqual(token, "{{full_name}}")

    def test_vault_redaction_and_substitution(self):
        """Verify two-way redaction and local substitution."""
        self.vault.register_secret("full_name", "Aarav Sharma")
        self.vault.register_secret("dob", "2005-04-05")

        raw_text = "Applicant Aarav Sharma born on 2005-04-05 is applying for scholarship."
        redacted = self.vault.redact(raw_text)

        # Redacted text should hide real values
        self.assertNotIn("Aarav Sharma", redacted)
        self.assertNotIn("2005-04-05", redacted)
        self.assertIn("{{full_name}}", redacted)
        self.assertIn("{{dob}}", redacted)

        # Local substitution should restore real values
        restored = self.vault.substitute(redacted)
        self.assertEqual(restored, raw_text)

    def test_mask_citizen_profile(self):
        """Verify sensitive citizen fields are masked while preserving non-sensitive ones."""
        self.vault.load_from_profile(self.citizen_data)
        masked = self.vault.mask_profile(self.citizen_data)

        # Sensitive fields masked
        self.assertEqual(masked["personal"]["full_name"], "{{full_name}}")
        self.assertEqual(masked["personal"]["dob"], "{{dob}}")
        self.assertEqual(masked["education"]["annual_income"], "{{annual_income}}")

        # Non-sensitive fields preserved
        self.assertEqual(masked["personal"]["category"], "General")
        self.assertEqual(masked["personal"]["course"], "B.Tech")
        self.assertEqual(masked["education"]["college"], "Demo Institute of Technology")

    def test_pii_leak_detection_catches_unmasked_value(self):
        """Verify scan_for_leaks detects any unmasked sensitive values in an LLM prompt."""
        self.vault.load_from_profile(self.citizen_data)

        # Prompt with accidental real name leak
        leaky_prompt = "Select the best match for citizen Aarav Sharma applying for course B.Tech."
        leaks = self.vault.scan_for_leaks(leaky_prompt)

        self.assertEqual(len(leaks), 1)
        self.assertEqual(leaks[0][0], "{{full_name}}")
        self.assertEqual(leaks[0][1], "Aarav Sharma")

        with self.assertRaises(PIILeakDetectedError):
            self.vault.assert_no_leaks(leaky_prompt, context_label="Gemini prompt")

    def test_pii_log_scan_clean(self):
        """Verify clean masked prompts pass the log-scan test with 0 leaks."""
        self.vault.load_from_profile(self.citizen_data)

        # Prompt using only placeholders
        safe_prompt = "Select the best match for citizen {{full_name}} applying for course B.Tech with income {{annual_income}}."
        leaks = self.vault.scan_for_leaks(safe_prompt)

        self.assertEqual(len(leaks), 0)
        # Should not raise exception
        self.vault.assert_no_leaks(safe_prompt, context_label="Clean prompt")

    def test_log_scan_against_all_sample_llm_prompts(self):
        """
        Feature F1 Requirement: scan stored/generated LLM request prompts
        for any sensitive value and fail if one appears.
        """
        self.vault.load_from_profile(self.citizen_data)
        masked = self.vault.mask_profile(self.citizen_data)

        # Simulate prompts that the agent sends to Gemini
        prompts = [
            f"Map course '{masked['personal']['course']}' to options ['B.Tech', 'B.Sc']",
            f"Map category '{masked['personal']['category']}' to options ['General', 'OBC']",
            f"Map education year '{masked['education']['course_year']}' to options ['First Year', 'Third Year']",
            f"Review verification for applicant {{full_name}} at college {masked['education']['college']}"
        ]

        total_leaks = 0
        for p in prompts:
            leaks = self.vault.scan_for_leaks(p)
            total_leaks += len(leaks)

        self.assertEqual(total_leaks, 0, f"Found {total_leaks} PII leaks in sample prompts!")


if __name__ == "__main__":
    unittest.main()
