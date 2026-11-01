import unittest
from pathlib import Path

from agent.universal_form_agent import UniversalFormAgent

ROOT = Path(__file__).resolve().parents[2]


class TestUniversalFormAgent(unittest.TestCase):
    def setUp(self):
        self.agent = UniversalFormAgent()

    def test_classify_field_intents(self):
        self.assertEqual(self.agent._classify_field_intent("Full name *"), "full_name")
        self.assertEqual(self.agent._classify_field_intent("Candidate Name"), "full_name")
        self.assertEqual(self.agent._classify_field_intent("Email Address"), "email")
        self.assertEqual(self.agent._classify_field_intent("Phone Number"), "phone")
        self.assertEqual(self.agent._classify_field_intent("Date of birth *"), "dob")
        self.assertEqual(self.agent._classify_field_intent("Annual family income (INR)"), "annual_income")
        self.assertEqual(self.agent._classify_field_intent("Previous exam percentage (%)"), "marks")
        self.assertEqual(self.agent._classify_field_intent("Current College / University"), "college")
        self.assertEqual(self.agent._classify_field_intent("Degree / Field of study"), "course")
        self.assertEqual(self.agent._classify_field_intent("Upload marksheet"), "marksheet_path")
        self.assertEqual(self.agent._classify_field_intent("Statement of Purpose"), "statement")
        self.assertEqual(self.agent._classify_field_intent("Driving Licence Number"), "dl_number")
        self.assertEqual(self.agent._classify_field_intent("DL number"), "dl_number")

    def test_profile_attributes_present(self):
        p = self.agent.profile
        self.assertIn("full_name", p)
        self.assertTrue(len(p["full_name"]) > 0)
        self.assertIn("dob", p)
        self.assertIn("college", p)
        self.assertIn("marks", p)
        self.assertIn("annual_income", p)
        self.assertIn("marksheet_path", p)


if __name__ == "__main__":
    unittest.main()
