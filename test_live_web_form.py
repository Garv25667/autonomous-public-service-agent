"""
Live Web Form Autofill Runner (test_live_web_form.py)
Runs the Universal Form Agent against any live public website or form URL.
Visibly highlights and types citizen data into fields in real time.
"""

import sys
import argparse
import asyncio
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from playwright.async_api import async_playwright
from agent.universal_form_agent import UniversalFormAgent


async def run_live_test(url: str, slow_mo: int = 600, wait_seconds: int = 15):
    print("\n" + "=" * 80)
    print(" UNIVERSAL FORM AGENT: LIVE WEB AUTOFILL RUNNER")
    print(f" Target Web URL: {url}")
    print("=" * 80)

    agent = UniversalFormAgent(slow_mo_ms=slow_mo)

    async with async_playwright() as p:
        print("\n[Browser] Launching Google Chromium in visible mode...")
        browser = await p.chromium.launch(
            headless=False,
            slow_mo=slow_mo,
            args=["--start-maximized"]
        )
        context = await browser.new_context(no_viewport=True)
        page = await context.new_page()

        try:
            print(f"[Browser] Navigating to: {url}...")
            await page.goto(url, timeout=30000, wait_until="domcontentloaded")
            await asyncio.sleep(1)

            # Execute universal form inspection and filling
            count = await agent.fill_page(page)

            print("\n=======================================================")
            print(f" LIVE AUTOFILL COMPLETE! {count} fields filled.")
            print("=======================================================")
            print(f"Leaving the browser open on your screen for {wait_seconds} seconds so you can see it...")
            await asyncio.sleep(wait_seconds)

        except Exception as e:
            print(f"[Error] {e}")
            await asyncio.sleep(5)
        finally:
            await browser.close()
            print("[Browser] Closed.\n")


def main():
    parser = argparse.ArgumentParser(description="Autofill any real web form with the Autonomous Agent")
    # Default to a live public form on the web
    parser.add_argument(
        "--url",
        default="https://httpbin.org/forms/post",
        help="Target webpage URL to autofill (e.g. a live public form URL)"
    )
    parser.add_argument("--slow-mo", type=int, default=500, help="Delay between actions in ms (default: 500)")
    parser.add_argument("--wait", type=int, default=15, help="Seconds to leave browser open after filling")
    args = parser.parse_args()

    asyncio.run(run_live_test(args.url, slow_mo=args.slow_mo, wait_seconds=args.wait))


if __name__ == "__main__":
    main()
