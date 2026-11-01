"""
Visible Browser Demonstration (run_visible.py)
Launches a visible Chromium window in slow motion so you can watch the agent
autonomously log in, type applicant details, upload documents, and submit.
"""

import sys
import time
import asyncio
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from playwright.async_api import async_playwright


async def main():
    portal_url = "http://127.0.0.1:5000"

    # Load synthetic citizen profile
    profile_path = ROOT / "data" / "citizen.json"
    with open(profile_path, "r", encoding="utf-8") as f:
        profile = json.load(f)

    personal = profile["personal"]
    education = profile["education"]
    marksheet_file = ROOT / education["marksheet_path"]

    print("\n=======================================================")
    print(" LAUNCHING AUTONOMOUS AGENT (VISIBLE SLOW-MO MODE)")
    print("=======================================================")
    print("Watch the Chromium window on your screen!\n")

    async with async_playwright() as p:
        # Launch visible browser with 600ms slow-mo between actions
        browser = await p.chromium.launch(headless=False, slow_mo=600)
        context = await browser.new_context()
        page = await context.new_page()

        # Auto-accept native JS confirm dialog on review page
        page.on("dialog", lambda dialog: asyncio.create_task(dialog.accept()))

        try:
            # 1. Login
            print("[1/5] Signing into portal as student...")
            await page.goto(f"{portal_url}/login")
            await page.locator("#username").fill("student")
            await page.locator("#password").fill("demo123")
            await page.get_by_role("button", name="Sign in securely").click()
            await page.wait_for_load_state("domcontentloaded")

            # 2. Personal Information
            print(f"[2/5] Filling Personal Details for {personal['full_name']}...")
            await page.locator("input[name='full_name']").fill(personal["full_name"])
            await page.locator("#dob").fill(personal["dob"])
            await page.locator("#category").select_option(label=personal["category"])
            await page.locator("#course").select_option(label=personal["course"])

            print("      Selecting cascading dropdowns: Maharashtra -> Pune -> Haveli...")
            await page.locator("#state").select_option(label=personal["state"])
            await asyncio.sleep(0.3)
            await page.locator("#district").select_option(label=personal["district"])
            await asyncio.sleep(0.3)
            await page.locator("#block").select_option(label=personal["block"])

            await page.get_by_role("button", name="Save & continue").click()
            await page.wait_for_load_state("domcontentloaded")

            # 3. Academic Details & Document Upload
            print(f"[3/5] Filling Academic Details & uploading marksheet...")
            await page.locator("#college").fill(education["college"])
            await page.locator("#course_year").select_option(label=education["course_year"])
            await page.locator("#marks").fill(str(education["marks"]))
            await page.locator("#annual_income").fill(str(education["annual_income"]))

            print(f"      Attaching document: {marksheet_file.name}...")
            upload = page.locator("#marksheet")
            await upload.set_input_files(str(marksheet_file))

            await page.get_by_role("button", name="Save & continue").click()
            await page.wait_for_load_state("domcontentloaded")

            # 4. Declaration
            print("[4/5] Checking legal declaration...")
            dec = page.locator("input[name='declaration']")
            await dec.check()

            await page.get_by_role("button", name="Continue to review").click()
            await page.wait_for_load_state("domcontentloaded")

            # 5. Review & Approval Gate
            print("[5/5] Reached Review Page! Citizen Approval Granted.")
            print("      Submitting application...")
            await page.get_by_role("button", name="Approve & submit application").click()
            await page.wait_for_url("**/receipt/**", timeout=15000)

            # Receipt Extracted
            receipt_el = page.locator("#receipt-id")
            receipt_id = await receipt_el.text_content()

            print("\n=======================================================")
            print(f" SUCCESS! Application Confirmed.")
            print(f" Extracted Receipt ID: {receipt_id.strip()}")
            print("=======================================================")
            print("Leaving the browser open on your screen for 15 seconds so you can see it...")
            await asyncio.sleep(15)

        finally:
            await browser.close()
            print("Browser closed.")


if __name__ == "__main__":
    asyncio.run(main())
