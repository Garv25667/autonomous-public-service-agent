import unittest
import tempfile
import os
from pathlib import Path

from agent.workflow_cache import WorkflowCache, CachedStep, WorkflowRecord


class TestStep11WorkflowCache(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_cache.sqlite"
        self.cache = WorkflowCache(db_path=self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_compute_page_fingerprint_deterministic(self):
        labels_1 = ["Full name *", "Date of birth *", "Category", "Current course"]
        labels_2 = ["category", "current course", "full name *", "date of birth *"]
        
        fp1 = self.cache.compute_page_fingerprint("/application/1", labels_1)
        fp2 = self.cache.compute_page_fingerprint("/application/1", labels_2)
        self.assertEqual(fp1, fp2)
        self.assertEqual(len(fp1), 16)

    def test_cache_miss_and_hit(self):
        fp = self.cache.compute_page_fingerprint("/application/1", ["Name", "DOB"])
        # Initially miss
        res = self.cache.get_workflow(fp)
        self.assertIsNone(res)
        self.assertEqual(self.cache.cache_misses, 1)

        # Save record
        record = WorkflowRecord(
            page_fingerprint=fp,
            portal_id="scholar_portal",
            url_pattern="/application/1",
            steps=[
                CachedStep(
                    step_id="step1_name",
                    intent="fill_name",
                    action_type="fill",
                    locator_strategy="label",
                    locator_target="Full name *",
                    value_ref="personal.full_name"
                )
            ]
        )
        self.cache.save_workflow(record)

        # Now hit
        hit = self.cache.get_workflow(fp)
        self.assertIsNotNone(hit)
        self.assertEqual(hit.page_fingerprint, fp)
        self.assertEqual(len(hit.steps), 1)
        self.assertEqual(hit.steps[0].step_id, "step1_name")
        self.assertEqual(self.cache.cache_hits, 1)

    def test_record_step_increments_and_appends(self):
        fp = self.cache.compute_page_fingerprint("/application/2", ["College", "Marks"])
        step1 = CachedStep(
            step_id="college_fill",
            intent="fill_college",
            action_type="fill",
            locator_strategy="label",
            locator_target="College / Institution *"
        )
        self.cache.record_step(fp, "/application/2", step1)

        # Record again: should update success_count
        self.cache.record_step(fp, "/application/2", step1)

        workflow = self.cache.get_workflow(fp)
        self.assertIsNotNone(workflow)
        self.assertEqual(len(workflow.steps), 1)
        self.assertEqual(workflow.steps[0].success_count, 2)

        # Add second step
        step2 = CachedStep(
            step_id="marks_fill",
            intent="fill_marks",
            action_type="fill",
            locator_strategy="label",
            locator_target="Previous examination marks (%)"
        )
        self.cache.record_step(fp, "/application/2", step2)

        workflow = self.cache.get_workflow(fp)
        self.assertEqual(len(workflow.steps), 2)

    def test_self_healing_step(self):
        fp = self.cache.compute_page_fingerprint("/application/1", ["Category"])
        step = CachedStep(
            step_id="cat_select",
            intent="select_category",
            action_type="select",
            locator_strategy="label",
            locator_target="Category"
        )
        self.cache.record_step(fp, "/application/1", step)

        # Simulate DOM rename: portal renamed Category label to "Applicant Category"
        healed = self.cache.heal_step(fp, "cat_select", new_locator_target="Applicant Category", new_strategy="label")
        self.assertTrue(healed)
        self.assertEqual(self.cache.healed_steps, 1)

        wf = self.cache.get_workflow(fp)
        self.assertEqual(wf.steps[0].locator_target, "Applicant Category")

    def test_cache_telemetry_stats(self):
        fp = self.cache.compute_page_fingerprint("/application/1", ["A", "B"])
        _ = self.cache.get_workflow(fp)  # Miss

        rec = WorkflowRecord(page_fingerprint=fp, url_pattern="/application/1", steps=[])
        self.cache.save_workflow(rec)
        _ = self.cache.get_workflow(fp)  # Hit

        stats = self.cache.get_stats()
        self.assertEqual(stats["cached_workflows"], 1)
        self.assertEqual(stats["cache_hits"], 1)
        self.assertEqual(stats["cache_misses"], 1)
        self.assertEqual(stats["hit_rate_percent"], 50.0)


if __name__ == "__main__":
    unittest.main()
