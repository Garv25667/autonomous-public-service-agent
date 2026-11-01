import unittest
import json
from pathlib import Path
from fastapi import HTTPException

from api.main import (
    app,
    get_profile,
    update_profile,
    check_eligibility,
    list_runs,
    get_run_details,
    serve_dashboard,
)
from agent.orchestrator import AgentOrchestrator
from agent.states import RunState, PlanStep
from agent.checkpoint import Checkpointer


class TestStep9ApiAndOrchestrator(unittest.TestCase):
    def setUp(self):
        self.orchestrator = AgentOrchestrator(headless=True, dry_run=True)

    def test_orchestrator_initializes_canonical_6_step_plan(self):
        plan = self.orchestrator.initialize_plan()
        self.assertEqual(len(plan), 6)
        step_names = [s.name for s in plan]
        self.assertIn("Portal Authentication", step_names)
        self.assertIn("Applicant Information", step_names)
        self.assertIn("Academic Details", step_names)
        self.assertIn("Applicant Declaration", step_names)
        self.assertIn("Final Review & Approval", step_names)
        self.assertIn("Receipt Extraction", step_names)

    def test_orchestrator_components_initialized(self):
        self.assertIsNotNone(self.orchestrator.guards)
        self.assertIsNotNone(self.orchestrator.vault)
        self.assertIsNotNone(self.orchestrator.checkpointer)
        self.assertIsNotNone(self.orchestrator.evaluator)
        self.assertIsNotNone(self.orchestrator.doc_processor)
        self.assertIsNotNone(self.orchestrator.mapper)
        self.assertIsNotNone(self.orchestrator.verifier)
        self.assertIsNotNone(self.orchestrator.recovery)
        self.assertIsNotNone(self.orchestrator.approval_gate)
        self.assertIsNotNone(self.orchestrator.receipt_extractor)
        self.assertTrue(self.orchestrator.dry_run)
        self.assertTrue(self.orchestrator.headless)

    def test_api_get_profile(self):
        profile = get_profile()
        self.assertIn("personal", profile)
        self.assertIn("education", profile)
        self.assertEqual(profile["personal"]["full_name"], "Aarav Sharma")
        self.assertEqual(profile["education"]["college"], "Demo Institute of Technology")

    def test_api_check_eligibility(self):
        result = check_eligibility()
        self.assertIn("eligible", result)
        self.assertTrue(result["eligible"])
        self.assertIn("reasons", result)

    def test_api_serve_dashboard(self):
        html = serve_dashboard()
        self.assertIn("Public Service Agent", html)
        self.assertIn("screencast-img", html)
        self.assertIn("log-stream", html)
        self.assertIn("human-gate-card", html)
        self.assertIn("receipt-card", html)

    def test_api_get_run_details_not_found(self):
        with self.assertRaises(HTTPException) as ctx:
            get_run_details("non-existent-run-id-99999")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_api_list_runs(self):
        runs = list_runs()
        self.assertIsInstance(runs, list)


if __name__ == "__main__":
    unittest.main()
