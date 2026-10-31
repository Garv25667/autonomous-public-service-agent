import tempfile
import unittest
from pathlib import Path

from agent.states import RunState, PlanStep, AuditEvent
from agent.checkpoint import Checkpointer
from agent.guards import (
    RuntimeGuards,
    LoopDetectedError,
    ActionBudgetExceededError,
    StepRetryExceededError,
    DoubleSubmissionError,
)


class TestStateAndGuards(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_runs.sqlite"
        self.checkpointer = Checkpointer(db_path=self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_run_state_audit_and_actions(self):
        """Verify RunState updates action budget and appends audit events."""
        plan = [
            PlanStep(step_id="login", name="Login", intent="Authenticate user"),
            PlanStep(step_id="step1", name="Personal Details", intent="Fill personal info"),
        ]
        state = RunState(plan=plan)
        self.assertEqual(state.total_actions, 0)
        self.assertEqual(state.current_step.step_id, "login")

        # Record audit event
        event = state.record_audit(
            action="fill",
            selector="input#username",
            value_summary="student",
            status="success"
        )
        self.assertEqual(state.total_actions, 1)
        self.assertEqual(len(state.audit), 1)
        self.assertEqual(event.step_id, "login")

    def test_checkpoint_persistence_lifecycle(self):
        """Verify RunState persists to SQLite and can be cleanly restored."""
        plan = [
            PlanStep(step_id="step1", name="Step 1", intent="First step"),
            PlanStep(step_id="step2", name="Step 2", intent="Second step"),
        ]
        state = RunState(run_id="run_test_123", plan=plan, step_index=1, status="needs_human")
        state.human_reason = "Waiting for CAPTCHA input"

        # Save checkpoint
        self.checkpointer.save(state)

        # Restore checkpoint
        restored = self.checkpointer.load("run_test_123")
        self.assertIsNotNone(restored)
        self.assertEqual(restored.run_id, "run_test_123")
        self.assertEqual(restored.status, "needs_human")
        self.assertEqual(restored.step_index, 1)
        self.assertEqual(restored.human_reason, "Waiting for CAPTCHA input")
        self.assertEqual(restored.current_step.step_id, "step2")

    def test_loop_detection_guard(self):
        """Verify loop detector flags when same page hash is seen 3 times consecutively."""
        guards = RuntimeGuards(loop_threshold=3)
        state = RunState()

        hash_a = guards.compute_page_hash("http://127.0.0.1:5000/step1", "Personal Form")
        hash_b = guards.compute_page_hash("http://127.0.0.1:5000/step2", "Academic Form")

        # Alternating pages: no loop
        guards.record_and_check_loop(state, hash_a)
        guards.record_and_check_loop(state, hash_b)
        guards.record_and_check_loop(state, hash_a)

        # 3 identical hashes in a row: should raise LoopDetectedError
        guards.record_and_check_loop(state, hash_a)
        with self.assertRaises(LoopDetectedError):
            guards.record_and_check_loop(state, hash_a)

    def test_action_budget_guard(self):
        """Verify action budget halts when total actions exceed limit."""
        guards = RuntimeGuards(max_action_budget=5)
        state = RunState()
        state.total_actions = 4
        guards.check_action_budget(state)  # 4 < 5, OK

        state.total_actions = 5
        with self.assertRaises(ActionBudgetExceededError):
            guards.check_action_budget(state)

    def test_step_retry_guard(self):
        """Verify step retry guard limits max retries to 3."""
        guards = RuntimeGuards(max_step_retries=3)
        state = RunState()
        state.retries_on_step = 2
        guards.check_step_retry(state)  # 2 < 3, OK

        state.retries_on_step = 3
        with self.assertRaises(StepRetryExceededError):
            guards.check_step_retry(state)

    def test_idempotency_double_submission_guard(self):
        """Verify idempotency guard prevents double submission."""
        guards = RuntimeGuards()
        state = RunState()
        guards.check_idempotency(state)  # Not submitted, OK

        # Simulate already submitted
        state.submitted = True
        state.receipt_id = "SCH-123456"
        with self.assertRaises(DoubleSubmissionError):
            guards.check_idempotency(state)


if __name__ == "__main__":
    unittest.main()
