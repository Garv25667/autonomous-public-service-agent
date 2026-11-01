import unittest
import json
import tempfile
from pathlib import Path

from benchmark import BenchmarkRunner, RunMetric, ScenarioSummary


class TestStep10Benchmark(unittest.TestCase):
    def setUp(self):
        self.runner = BenchmarkRunner(mode="sim")

    def test_runner_initialization_sim_mode(self):
        self.assertEqual(self.runner.mode, "sim")
        self.assertEqual(len(self.runner.SCENARIOS), 6)
        self.assertIn("base", self.runner.SCENARIOS)
        self.assertIn("gate", self.runner.SCENARIOS)
        self.assertIn("flaky_500", self.runner.SCENARIOS)

    def test_run_simulation_base_scenario(self):
        metric = self.runner.run_simulation_trial("base", trial=1)
        self.assertTrue(metric.task_success)
        self.assertTrue(metric.db_verified)
        self.assertEqual(metric.field_accuracy, 100.0)
        self.assertEqual(metric.pii_leaks, 0)
        self.assertEqual(metric.unapproved_submissions, 0)
        self.assertIsNotNone(metric.receipt_id)
        self.assertTrue(metric.receipt_id.startswith("SCH-"))

    def test_run_simulation_popup_scenario(self):
        metric = self.runner.run_simulation_trial("popup", trial=1)
        self.assertTrue(metric.task_success)
        self.assertTrue(metric.fault_injected)
        self.assertTrue(metric.fault_recovered)
        self.assertEqual(metric.pii_leaks, 0)

    def test_run_simulation_expire_session_scenario(self):
        metric = self.runner.run_simulation_trial("expire_session", trial=1)
        self.assertTrue(metric.task_success)
        self.assertTrue(metric.fault_injected)
        self.assertTrue(metric.fault_recovered)
        self.assertEqual(metric.pii_leaks, 0)

    def test_run_simulation_flaky_500_scenario(self):
        metric = self.runner.run_simulation_trial("flaky_500", trial=1)
        self.assertTrue(metric.task_success)
        self.assertTrue(metric.fault_injected)
        self.assertTrue(metric.fault_recovered)
        self.assertEqual(metric.pii_leaks, 0)

    def test_run_simulation_gate_scenario(self):
        metric = self.runner.run_simulation_trial("gate", trial=1)
        self.assertTrue(metric.task_success)
        self.assertTrue(metric.fault_injected)
        self.assertTrue(metric.fault_recovered)
        self.assertGreaterEqual(metric.human_interventions, 1)
        self.assertEqual(metric.pii_leaks, 0)

    def test_run_simulation_legacy_scenario(self):
        metric = self.runner.run_simulation_trial("legacy", trial=1)
        self.assertTrue(metric.task_success)
        self.assertTrue(metric.fault_recovered)
        self.assertEqual(metric.field_accuracy, 100.0)
        self.assertEqual(metric.pii_leaks, 0)

    def test_summarize_and_metrics_contract(self):
        metrics = self.runner.run_benchmark(runs_per_scenario=2, scenarios=["base", "popup"])
        self.assertEqual(len(metrics), 4)

        summaries = self.runner.summarize(metrics)
        self.assertEqual(len(summaries), 2)

        base_summary = next(s for s in summaries if s.scenario == "base")
        self.assertEqual(base_summary.runs, 2)
        self.assertEqual(base_summary.task_success_rate, 100.0)
        self.assertEqual(base_summary.pii_leaks, 0)
        self.assertEqual(base_summary.unapproved_submissions, 0)


if __name__ == "__main__":
    unittest.main()
