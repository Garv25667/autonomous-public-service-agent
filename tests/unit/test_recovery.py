import unittest
from agent.verifier import VerificationResult
from agent.states import RunState, PlanStep
from agent.recovery import RecoveryHandler, RecoveryAction


class TestRecoveryHandler(unittest.TestCase):

    def setUp(self):
        self.handler = RecoveryHandler(max_step_retries=3)

    def test_pick_strategy_no_action_needed(self):
        """Verify no recovery needed when verification succeeds."""
        res = VerificationResult(success=True, issue_type="none")
        state = RunState()
        strategy = self.handler.pick_strategy(res, state)
        self.assertEqual(strategy, "no_action_needed")

    def test_pick_strategy_popup_dismissal(self):
        """Verify popup_or_modal issues route to dismiss_popup."""
        res = VerificationResult(success=False, issue_type="popup_or_modal")
        state = RunState()
        strategy = self.handler.pick_strategy(res, state)
        self.assertEqual(strategy, "dismiss_popup")

    def test_pick_strategy_session_expired(self):
        """Verify session_expired routes to relogin_and_resume."""
        res = VerificationResult(success=False, issue_type="session_expired")
        state = RunState(step_index=2)
        strategy = self.handler.pick_strategy(res, state)
        self.assertEqual(strategy, "relogin_and_resume")

    def test_pick_strategy_server_error_500(self):
        """Verify 500 error routes to backoff_and_retry."""
        res = VerificationResult(success=False, issue_type="server_error_500")
        state = RunState()
        strategy = self.handler.pick_strategy(res, state)
        self.assertEqual(strategy, "backoff_and_retry")

    def test_pick_strategy_human_gate(self):
        """Verify CAPTCHA / OTP gate routes to pause_for_human."""
        res = VerificationResult(success=False, issue_type="human_gate")
        state = RunState()
        strategy = self.handler.pick_strategy(res, state)
        self.assertEqual(strategy, "pause_for_human")

    def test_pick_strategy_validation_error(self):
        """Verify validation errors route to fix_field_and_retry."""
        res = VerificationResult(success=False, issue_type="validation_error", alert_text="Missing name")
        state = RunState()
        strategy = self.handler.pick_strategy(res, state)
        self.assertEqual(strategy, "fix_field_and_retry")

    def test_pick_strategy_mismatch_routes_to_reload(self):
        """Verify URL and heading mismatches route to reload_and_retry."""
        res = VerificationResult(success=False, issue_type="url_mismatch")
        state = RunState()
        strategy = self.handler.pick_strategy(res, state)
        self.assertEqual(strategy, "reload_and_retry")

    def test_pick_strategy_escalates_on_exhausted_retries(self):
        """Verify handler escalates to failure when retry budget is exceeded."""
        res = VerificationResult(success=False, issue_type="popup_or_modal")
        state = RunState(retries_on_step=3)
        strategy = self.handler.pick_strategy(res, state)
        self.assertEqual(strategy, "escalate_failure")

    def test_apply_pause_for_human_gate(self):
        """Verify applying pause_for_human transitions state to needs_human."""
        res = VerificationResult(success=False, issue_type="human_gate")
        state = RunState(run_id="run_gate_test")

        action = self.handler.apply_recovery_state(
            strategy="pause_for_human",
            result=res,
            state=state
        )

        self.assertTrue(action.success)
        self.assertTrue(action.needs_human)
        self.assertEqual(state.status, "needs_human")
        self.assertIn("CAPTCHA", state.human_reason)
        self.assertEqual(len(state.audit), 1)
        self.assertEqual(state.audit[0].action, "pause_for_human")

    def test_apply_recovery_retries_increment(self):
        """Verify applying any recovery strategy increments retries_on_step."""
        res = VerificationResult(success=False, issue_type="popup_or_modal")
        state = RunState()
        self.assertEqual(state.retries_on_step, 0)

        action = self.handler.apply_recovery_state("dismiss_popup", res, state)
        self.assertTrue(action.success)
        self.assertTrue(action.retry_action)
        self.assertEqual(state.retries_on_step, 1)


if __name__ == "__main__":
    unittest.main()
