import unittest
import io
from contextlib import redirect_stdout
from pathlib import Path

from demo import run_demo

ROOT = Path(__file__).resolve().parents[2]


class TestStep12DemoAndDocs(unittest.TestCase):

    def test_run_demo_popup_scenario(self):
        f = io.StringIO()
        with redirect_stdout(f):
            run_demo(scenario="popup", headless=True)
        out = f.getvalue()
        self.assertIn("AUTONOMOUS PUBLIC SERVICE AGENT", out)
        self.assertIn("Aarav Sharma", out)
        self.assertIn("ELIGIBLE FOR MERIT SCHOLARSHIP", out)
        self.assertIn("popup_or_modal", out)
        self.assertIn("dismiss_popup", out)
        self.assertIn("APPROVED", out)
        self.assertIn("SCH-B49D12F0", out)
        self.assertIn("TARGET MET: 0 LEAKS", out)

    def test_run_demo_gate_scenario(self):
        f = io.StringIO()
        with redirect_stdout(f):
            run_demo(scenario="gate", headless=True)
        out = f.getvalue()
        self.assertIn("Security gate detected", out)
        self.assertIn("Human Handoff", out)

    def test_run_demo_500_scenario(self):
        f = io.StringIO()
        with redirect_stdout(f):
            run_demo(scenario="flaky_500", headless=True)
        out = f.getvalue()
        self.assertIn("server_error_500", out)
        self.assertIn("backoff_and_retry", out)

    def test_run_demo_session_expiry_scenario(self):
        f = io.StringIO()
        with redirect_stdout(f):
            run_demo(scenario="expire_session", headless=True)
        out = f.getvalue()
        self.assertIn("session_expired", out)
        self.assertIn("relogin_and_resume", out)

    def test_readme_integrity(self):
        readme_path = ROOT / "README.md"
        self.assertTrue(readme_path.exists())
        with open(readme_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check required sections per Playbook
        self.assertIn("Autonomous Public Service Agent", content)
        self.assertIn("Architecture", content)
        self.assertIn("Benchmark", content)
        self.assertIn("Zero-PII", content)
        self.assertIn("Quickstart", content)


if __name__ == "__main__":
    unittest.main()
