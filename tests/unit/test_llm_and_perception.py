import json
import tempfile
import unittest
from pathlib import Path

from agent.llm.cache import DiskCache
from agent.llm.schemas import DropdownMatch, CitizenProfile
from agent.llm.client import LLMClient, QuotaExceededError
from agent.perception import SemanticMapper


class TestStep3(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_dir = Path(self.temp_dir.name)
        self.disk_cache = DiskCache(cache_dir=self.cache_dir)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_citizen_profile_schema_validation(self):
        """Verify CitizenProfile Pydantic schema validates the real citizen.json."""
        root = Path(__file__).resolve().parents[2]
        citizen_path = root / "data" / "citizen.json"
        with open(citizen_path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        profile = CitizenProfile.model_validate(raw)
        self.assertTrue(len(profile.personal.full_name) > 0)
        self.assertEqual(profile.personal.category, "General")
        self.assertEqual(profile.education.course_year, "Third Year")

    def test_disk_cache_roundtrip(self):
        """Verify DiskCache hashes and retrieves structured data."""
        model = "gemini-2.5-flash"
        prompt = "match category"
        payload = {"choice": "General", "confidence": 1.0, "evidence": "cached"}

        # Cache miss
        self.assertIsNone(self.disk_cache.get(model, prompt))

        # Cache set
        self.disk_cache.set(model, prompt, payload)

        # Cache hit
        hit = self.disk_cache.get(model, prompt)
        self.assertIsNotNone(hit)
        self.assertEqual(hit["choice"], "General")

    def test_llm_client_call_budget_guard(self):
        """Verify LLMClient halts gracefully when max_calls_per_run is reached."""
        client = LLMClient(
            max_calls_per_run=2,
            cache_dir=self.cache_dir,
            api_key="dummy-key-not-called"
        )

        # Populate cache for 2 prompts
        for i in range(2):
            self.disk_cache.set(
                client.model,
                f"prompt {i}",
                {"choice": f"Option {i}", "confidence": 1.0, "evidence": "test"}
            )

        # These two are cache hits (should not increment calls_count)
        res1 = client.generate_json(DropdownMatch, "prompt 0")
        res2 = client.generate_json(DropdownMatch, "prompt 1")
        self.assertEqual(client.calls_count, 0)
        self.assertEqual(res1.choice, "Option 0")

        # Simulate that calls_count reached limit
        client.calls_count = 2
        with self.assertRaises(QuotaExceededError):
            client.generate_json(DropdownMatch, "uncached prompt")

    def test_semantic_mapper_tier1_exact_match(self):
        """Verify Tier 1 exact match (case-insensitive) gives 1.0 confidence."""
        mapper = SemanticMapper()
        options = ["General", "OBC", "SC", "ST"]
        res = mapper.match_dropdown("general", options, field_label="Category")
        self.assertEqual(res.choice, "General")
        self.assertEqual(res.confidence, 1.0)
        self.assertIn("Tier 1", res.evidence)

    def test_semantic_mapper_tier2_synonym_match(self):
        """Verify Tier 2 synonym lookup resolves aliases."""
        mapper = SemanticMapper()
        options = ["Bachelor of Technology", "Bachelor of Science", "Master of Arts"]
        res = mapper.match_dropdown("B.Tech", options, field_label="Course")
        self.assertEqual(res.choice, "Bachelor of Technology")
        self.assertEqual(res.confidence, 0.95)
        self.assertIn("Tier 2", res.evidence)

    def test_semantic_mapper_tier3_fuzzy_match(self):
        """Verify Tier 3 fuzzy matching via rapidfuzz."""
        mapper = SemanticMapper()
        options = ["Maharashtra", "Madhya Pradesh", "Meghalaya"]
        # Typo: Maharashtr (missing 'a')
        res = mapper.match_dropdown("Maharashtr", options, field_label="State")
        self.assertEqual(res.choice, "Maharashtra")
        self.assertGreaterEqual(res.confidence, 0.8)
        self.assertIn("Tier 3", res.evidence)

    def test_semantic_mapper_no_match_rejection(self):
        """Verify completely unrelated values return None without hallucinating."""
        mapper = SemanticMapper()
        options = ["First Year", "Second Year", "Third Year"]
        res = mapper.match_dropdown("Aerospace Engineering", options, field_label="Year")
        self.assertIsNone(res.choice)
        self.assertLess(res.confidence, mapper.confidence_threshold)


if __name__ == "__main__":
    unittest.main()
