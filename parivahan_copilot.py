"""
Parivahan Sarathi Live Co-Pilot CLI (parivahan_copilot.py)
Automated navigator for Driving License Renewal on the official
Ministry of Road Transport and Highways portal (sarathi.parivahan.gov.in).
"""

import sys
import argparse
import asyncio
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.parivahan_assistant import ParivahanAssistant


def main():
    parser = argparse.ArgumentParser(description="Parivahan Sarathi DL Renewal Co-Pilot")
    parser.add_argument("--state", default=None, help="State name to select (e.g. Maharashtra, Delhi, Uttar Pradesh, Rajasthan)")
    parser.add_argument("--headless", action="store_true", default=False, help="Run browser in headless mode")
    parser.add_argument("--non-interactive", action="store_true", default=False, help="Do not wait for Enter key")
    args = parser.parse_args()

    print("\n" + "=" * 80)
    print(" PARIVAHAN SARATHI — DRIVING LICENSE (DL) RENEWAL CO-PILOT")
    print(" Official Portal: sarathi.parivahan.gov.in | MoRTH, Govt of India")
    print("=" * 80)

    assistant = ParivahanAssistant()

    # Phase 1: MoRTH Policy Pre-Check
    print("\n[Phase 1] Evaluating MoRTH Driving License Renewal Regulations...")
    assessment = assistant.evaluate_dl_renewal()

    if assessment.eligible:
        print(f"          [PASS] Status: ELIGIBLE FOR ONLINE DL RENEWAL")
        print(f"          Service: {assessment.service_name}")
        for item in assessment.actionable_checklist:
            print(f"          - {item}")
    else:
        print(f"          [FAIL] Status: INELIGIBLE")
        for r in assessment.reasons:
            print(f"          - {r}")
        return

    # Phase 2: Document Constraints Check (<= 500 KB)
    print("\n[Phase 2] Checking Document Specifications (Parivahan <= 500 KB Rule)...")
    for doc in assessment.required_documents:
        cond = doc.get("conditional", "")
        cond_str = f" [Condition: {cond}]" if cond else ""
        print(f"          - {doc['name']}: {doc['description']} (Limit: {doc['max_size_kb']} KB){cond_str}")

    # Phase 3: Zero-PII Protection
    print("\n[Phase 3] Zero-PII Secret Vault Tokenization...")
    personal = assistant.profile.get("personal", {})
    target_state = args.state or personal.get("state", "Maharashtra")
    print(f"          Applicant:  {personal.get('full_name')} (DOB: {personal.get('dob')})")
    print(f"          State:      {target_state}")
    print("          Personal identifiers will remain strictly local in your browser.")

    # Phase 4: Launch Live Portal Session
    print("\n[Phase 4] Launching Visible Chromium Co-Pilot Session...")
    print(f"          Target URL: {assistant.PARIVAHAN_URL}")
    print(f"          Action:     Autonomously selecting state '{target_state}'...")

    try:
        asyncio.run(assistant.launch_parivahan_session(
            state_name=target_state,
            headless=args.headless,
            non_interactive=args.non_interactive
        ))
    except KeyboardInterrupt:
        print("\n[Parivahan Co-Pilot] Session cancelled by user.")
    except Exception as e:
        print(f"\n[Parivahan Co-Pilot] Notice: {e}")

    print("\n=======================================================")
    print(" Parivahan Sarathi Co-Pilot Session Completed.")
    print("=======================================================\n")


if __name__ == "__main__":
    main()
