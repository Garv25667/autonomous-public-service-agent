import unittest
from pathlib import Path

from agent.parivahan_assistant import ParivahanAssistant
from agent.service_catalog import ServiceAssessment

ROOT = Path(__file__).resolve().parents[2]


class TestParivahanAssistant(unittest.TestCase):
    def setUp(self):
        self.assistant = ParivahanAssistant()

    def test_parivahan_initialization(self):
        self.assertIsNotNone(self.assistant.profile)
        self.assertIsNotNone(self.assistant.catalog)
        self.assertIn("sarathi.parivahan.gov.in", self.assistant.PARIVAHAN_URL)

    def test_evaluate_dl_renewal(self):
        assessment = self.assistant.evaluate_dl_renewal()
        self.assertIsInstance(assessment, ServiceAssessment)
        self.assertTrue(assessment.eligible)
        self.assertEqual(assessment.service_id, "license_renewal")
        self.assertGreater(len(assessment.required_documents), 0)

    def test_parivahan_checklist_generation(self):
        assessment = self.assistant.evaluate_dl_renewal()
        self.assertTrue(any("Age requirement satisfied" in c for c in assessment.actionable_checklist))
        self.assertTrue(any("supported on Parivahan Sarathi" in c for c in assessment.actionable_checklist))


if __name__ == "__main__":
    unittest.main()
