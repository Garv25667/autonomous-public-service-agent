"""
Real Parivahan Sarathi DL Assistant (test_real_dl.py)
Automates driving license lookup and renewal intake on the real
Ministry of Road Transport and Highways portal (sarathi.parivahan.gov.in).
Keeps all personal data 100% local on your machine.
"""

import sys
import asyncio
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from playwright.async_api import async_playwright


async def run_dl_assistant(state_name: str, dl_number: str, dob: str):
    print("\n" + "=" * 80)
    print(" PARIVAHAN SARATHI — LIVE DRIVING LICENSE (DL) ASSISTANT")
    print(" Official Portal: sarathi.parivahan.gov.in | MoRTH, Govt of India")
    print("=" * 80)
    print(f" Target State:     {state_name}")
    print(f" Target DL Number: {dl_number}")
    print(f" Date of Birth:    {dob}")
    print(" Privacy Notice:   Your credentials stay strictly on your local computer.\n")

    parivahan_url = "https://sarathi.parivahan.gov.in/sarathiservice/stateSelection.do"

    async with async_playwright() as p:
        print("[Browser] Launching Google Chromium in visible mode...")
        browser = await p.chromium.launch(
            headless=False,
            slow_mo=600,
            args=["--start-maximized"]
        )
        context = await browser.new_context(
            no_viewport=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            # 1. Open State Selection
            print(f"[Step 1] Navigating to: {parivahan_url}...")
            await page.goto(parivahan_url, timeout=40000, wait_until="domcontentloaded")
            await asyncio.sleep(1.5)

            # 2. Select State
            print(f"[Step 2] Selecting State '{state_name}' from government dropdown...")
            state_select = page.locator("select[name='stName'], select#stName, select").first
            if await state_select.is_visible():
                await state_select.evaluate("el => el.style.outline = '3px solid #00bcd4'")
                try:
                    await state_select.select_option(label=state_name)
                    print(f"         [OK] State '{state_name}' selected!")
                except Exception:
                    options = await state_select.locator("option").all_inner_texts()
                    match = next((o for o in options if state_name.lower() in o.lower()), None)
                    if match:
                        await state_select.select_option(label=match)
                        print(f"         [OK] Matched state: '{match}'")

            await page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(2)

            # 3. Dismiss any initial Parivahan modal/popup banner if present
            close_btn = page.locator(".modal.show button.close, [data-dismiss='modal'], button:has-text('Close')").first
            if await close_btn.is_visible():
                print("[Step 2b] Dismissing portal announcement banner...")
                await close_btn.click()
                await asyncio.sleep(1)

            # 4. Click DL Services / Apply for DL Renewal
            print("[Step 3] Locating 'Apply for DL Renewal' or 'Services on DL'...")
            service_link = page.locator("a:has-text('Apply for DL Renewal'), a:has-text('Services on DL'), a:has-text('Apply Online')").first
            if await service_link.is_visible():
                await service_link.evaluate("el => el.style.outline = '3px solid #00c853'")
                print("         [OK] Clicking into DL Services...")
                await service_link.click()
                await page.wait_for_load_state("domcontentloaded")
                await asyncio.sleep(2)

            # 5. Check if on Instructions page and click Continue
            continue_btn = page.locator("input[value='Continue'], button:has-text('Continue'), a:has-text('Continue')").first
            if await continue_btn.is_visible():
                print("[Step 4] On Instructions page -> Clicking Continue...")
                await continue_btn.evaluate("el => el.style.outline = '3px solid #00c853'")
                await continue_btn.click()
                await page.wait_for_load_state("domcontentloaded")
                await asyncio.sleep(2)

            # 6. Fill Driving License Number & Date of Birth
            print("[Step 5] Looking for DL Number & Date of Birth input fields...")
            dl_input = page.locator("input[name*='dl'], input[id*='dl'], input[placeholder*='DL'], input[placeholder*='Licence']").first
            dob_input = page.locator("input[name*='dob'], input[id*='dob'], input[type='date'], input[placeholder*='DOB']").first

            if await dl_input.is_visible():
                print(f"         [Typing] Entering DL Number into government input...")
                await dl_input.evaluate("el => el.style.outline = '3px solid #00c853'")
                await dl_input.fill(dl_number.strip())

            if await dob_input.is_visible():
                print(f"         [Typing] Entering Date of Birth ({dob})...")
                await dob_input.evaluate("el => el.style.outline = '3px solid #00c853'")
                await dob_input.fill(dob.strip())

            print("\n=======================================================")
            print(" HUMAN HANDOFF: SOLVE THE PARIVAHAN CAPTCHA")
            print("=======================================================")
            print("1. Look at the open Google Chrome window on your screen.")
            print("2. Type the 5-character visual CAPTCHA code into the box.")
            print("3. Click 'Get DL Details' button.")
            print("4. Watch the official MoRTH database return your live license details!")
            print("=======================================================\n")

            # Keep window open for the user to complete captcha and inspect their license record
            await asyncio.to_thread(input, ">> Press [ENTER] in this terminal when you are done viewing your details: ")
            print("[Browser] Finishing session...")

        except Exception as e:
            print(f"[Notice] {e}")
            await asyncio.to_thread(input, ">> Press [ENTER] to exit: ")
        finally:
            await browser.close()
            print("[Browser] Closed.\n")


def main():
    print("\n" + "=" * 70)
    print(" LIVE PARIVAHAN SARATHI ASSISTANT — CREDENTIAL SETUP")
    print("=" * 70)
    print("Please enter your details below (they are used ONLY locally in your browser):\n")

    state = input("1. Enter your State (e.g. Maharashtra, Delhi, Uttar Pradesh, Karnataka): ").strip()
    if not state:
        state = "Maharashtra"

    dl_number = input("2. Enter your Driving Licence Number (e.g. MH1220180012345): ").strip()
    if not dl_number:
        print("Error: Driving Licence Number is required.")
        return

    dob = input("3. Enter your Date of Birth (DD-MM-YYYY or YYYY-MM-DD): ").strip()
    if not dob:
        print("Error: Date of Birth is required.")
        return

    asyncio.run(run_dl_assistant(state_name=state, dl_number=dl_number, dob=dob))


if __name__ == "__main__":
    main()
