"""
National Scholarship Portal (NSP) Live Co-Pilot (nsp_copilot.py)
Assists citizens on the real official portal (scholarships.gov.in)
with document pre-flight (<= 200 KB), policy evaluation, and assisted form entry.
"""

import sys
import asyncio
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.nsp_assistant import NSPAssistant


def main():
    print("\n" + "=" * 80)
    print(" NATIONAL SCHOLARSHIP PORTAL (NSP) — ASSISTED AGENT CO-PILOT")
    print(" Target: scholarships.gov.in | Scheme: Central Sector Scheme (DoHE)")
    print("=" * 80)

    assistant = NSPAssistant()

    # Phase 1: Real Policy Pre-Check
    print("\n[Phase 1] Evaluating Official NSP Central Sector Scheme Guidelines...")
    summary = assistant.run_preflight_audit()

    if summary.eligible:
        print(f"          [PASS] Status: ELIGIBLE FOR CENTRAL SECTOR SCHOLARSHIP")
        print(f"          Scheme: {summary.scheme_name}")
    else:
        print(f"          [FAIL] Status: INELIGIBLE")
        for r in summary.reasons:
            print(f"          - {r}")
        print("\nPlease update citizen profile before proceeding to the live portal.")
        return

    # Phase 2: Real Document Constraints (<= 200 KB)
    print("\n[Phase 2] Validating Document Readiness (Strict NSP <= 200 KB Rule)...")
    if summary.document_valid:
        print(f"          [PASS] File Size: {summary.document_size_kb} KB (Complies with 200 KB limit)")
        print(f"          Status: Ready for portal upload.")
    else:
        print(f"          [WARNING] {summary.document_message}")
        print(f"          NSP will reject uploads larger than 200 KB.")

    # Phase 3: Zero-PII Protection
    print("\n[Phase 3] Zero-PII Secret Vault Tokenization...")
    print(f"          Tokenized Name:    {summary.sanitized_profile['personal']['full_name']}")
    print(f"          Tokenized DOB:     {summary.sanitized_profile['personal']['dob']}")
    print(f"          Tokenized Income:  {summary.sanitized_profile['education']['annual_income']}")
    print("          Real citizen identifiers will only be typed locally in your browser.")

    # Phase 4: Launch Live Portal Session
    print("\n[Phase 4] Launching Visible Chromium Co-Pilot Session...")
    print("          Target URL: https://scholarships.gov.in")
    print("          Safety Rule: The agent operates as an assisted co-pilot.")
    print("                       You retain 100% control over logins and final submission.")

    try:
        asyncio.run(assistant.launch_assisted_session("https://scholarships.gov.in"))
    except KeyboardInterrupt:
        print("\n[NSP Co-Pilot] Session cancelled by user.")
    except Exception as e:
        print(f"\n[NSP Co-Pilot] Notice: {e}")

    print("\n=======================================================")
    print(" NSP Co-Pilot Session Completed.")
    print("=======================================================\n")


if __name__ == "__main__":
    main()
