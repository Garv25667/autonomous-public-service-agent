import unittest
import json
from pathlib import Path

from agent.service_catalog import ServiceCatalog, ServiceAssessment

ROOT = Path(__file__).resolve().parents[2]


class TestServiceCatalog(unittest.TestCase):
    def setUp(self):
        self.catalog = ServiceCatalog()
        profile_path = ROOT / "data" / "citizen.json"
        with open(profile_path, "r", encoding="utf-8") as f:
            self.profile = json.load(f)

    def test_list_services(self):
        services = self.catalog.list_services()
        self.assertGreaterEqual(len(services), 3)
        service_ids = [s.service_id for s in services]
        self.assertIn("scholarship", service_ids)
        self.assertIn("license_renewal", service_ids)
        self.assertIn("subsidy_claim", service_ids)

    def test_evaluate_scholarship_service(self):
        res = self.catalog.evaluate_service("scholarship", self.profile)
        self.assertIsInstance(res, ServiceAssessment)
        self.assertTrue(res.eligible)
        self.assertIn("National Merit Scholarship", res.friendly_explanation)

    def test_evaluate_license_renewal_service(self):
        res = self.catalog.evaluate_service("license_renewal", self.profile)
        self.assertIsInstance(res, ServiceAssessment)
        self.assertTrue(res.eligible)
        self.assertEqual(res.service_id, "license_renewal")
        self.assertIn("sarathi.parivahan.gov.in", res.portal_url)
        self.assertGreater(len(res.actionable_checklist), 0)

    def test_evaluate_license_renewal_underage(self):
        profile = dict(self.profile)
        profile["personal"] = dict(profile["personal"])
        profile["personal"]["dob"] = "2015-01-01"  # Age ~11
        res = self.catalog.evaluate_service("license_renewal", profile)
        self.assertFalse(res.eligible)
        self.assertTrue(any("below minimum required age" in r for r in res.reasons))

    def test_evaluate_subsidy_service(self):
        res = self.catalog.evaluate_service("subsidy_claim", self.profile)
        self.assertIsInstance(res, ServiceAssessment)
        # Income is 450,000, subsidy limit is 250,000 -> should be ineligible
        self.assertFalse(res.eligible)
        self.assertTrue(any("exceeds welfare limit" in r for r in res.reasons))

    def test_invalid_service_raises_error(self):
        with self.assertRaises(ValueError):
            self.catalog.evaluate_service("invalid_unknown_service", self.profile)


if __name__ == "__main__":
    unittest.main()
