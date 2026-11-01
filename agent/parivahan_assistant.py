"""
Parivahan Sarathi Driving License Assistant (agent/parivahan_assistant.py)
Automated navigator and assisted co-pilot for the Ministry of Road Transport and Highways (MoRTH)
Parivahan Sarathi portal (sarathi.parivahan.gov.in).
"""

import sys
import json
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]

from agent.service_catalog import ServiceCatalog, ServiceAssessment
from agent.tools.secrets import SecretVault
from agent.tools.docs import DocumentProcessor

try:
    from playwright.async_api import async_playwright, Page, Browser
except ImportError:
    pass


class ParivahanAssistant:
    """
    Assisted Co-Pilot for MoRTH Parivahan Sarathi (sarathi.parivahan.gov.in):
    1. Pre-checks eligibility from rules/license_renewal.yaml.
    2. Validates document format and <= 500 KB size requirement.
    3. Launches visible Chromium to stateSelection.do.
    4. Automatically selects the citizen's state from the dropdown.
    5. Navigates to DL Services / Renewal.
    6. Pauses for human CAPTCHA and OTP handoff.
    """

    PARIVAHAN_URL = "https://sarathi.parivahan.gov.in/sarathiservice/stateSelection.do"

    def __init__(self, profile_path: Optional[Path] = None):
        self.profile_path = profile_path or (ROOT / "data" / "citizen.json")
        self.profile = self._load_profile()
        self.catalog = ServiceCatalog()
        self.vault = SecretVault()
        self.doc_processor = DocumentProcessor()

    def _load_profile(self) -> Dict[str, Any]:
        with open(self.profile_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def evaluate_dl_renewal(self) -> ServiceAssessment:
        """Evaluates driving license renewal eligibility against MoRTH guidelines."""
        return self.catalog.evaluate_service("license_renewal", self.profile)

    async def launch_parivahan_session(
        self,
        state_name: Optional[str] = None,
        headless: bool = False,
        non_interactive: bool = False
    ):
        """
        Launches visible browser session directed at Parivahan Sarathi:
        1. Navigates to stateSelection.do.
        2. Automatically chooses the citizen's State.
        3. Enters the Services menu.
        4. Pauses for human CAPTCHA/DL verification.
        """
        personal = self.profile.get("personal", {})
        target_state = state_name or personal.get("state", "Maharashtra")

        print(f"\n[Parivahan Co-Pilot] Target State: {target_state}")
        print(f"[Parivahan Co-Pilot] Launching Google Chromium (headless={headless})...")

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=headless,
                    slow_mo=500,
                    args=["--no-sandbox", "--disable-dev-shm-usage"] + (["--start-maximized"] if not headless else [])
                )
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 800} if headless else None,
                    no_viewport=not headless,
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                )
                page = await context.new_page()

                try:
                    print(f"[Parivahan Co-Pilot] Navigating to: {self.PARIVAHAN_URL}...")
                    try:
                        await page.goto(self.PARIVAHAN_URL, timeout=30000, wait_until="domcontentloaded")
                        await asyncio.sleep(1.5)
                    except Exception as net_err:
                        print(f"[Parivahan Co-Pilot] Gateway notice: {net_err}")
                        print(f"                     Direct Portal Link: {self.PARIVAHAN_URL}")

                    # Find state selector dropdown
                    print(f"[Parivahan Co-Pilot] Selecting State '{target_state}' on official MoRTH portal...")
                    state_select = page.locator("select[name='stName'], select#stName, select").first

                    if await state_select.is_visible(timeout=5000):
                        # Highlight state selector with cyan outline
                        await state_select.evaluate("el => el.style.outline = '3px solid #00bcd4'")
                        
                        # Try selecting by label, then value
                        try:
                            await state_select.select_option(label=target_state)
                            print(f"[Parivahan Co-Pilot] State '{target_state}' selected successfully!")
                        except Exception:
                            # Fallback case-insensitive match
                            options = await state_select.locator("option").all_inner_texts()
                            match = next((o for o in options if target_state.lower() in o.lower()), None)
                            if match:
                                await state_select.select_option(label=match)
                                print(f"[Parivahan Co-Pilot] Matched state option: '{match}'")

                        await page.wait_for_load_state("domcontentloaded")
                        await asyncio.sleep(2)

                    print("\n[Parivahan Co-Pilot] Looking for DL Services & Renewal options...")
                    # Search for "Apply for DL Renewal" or "Services on DL"
                    dl_buttons = page.locator("a:has-text('Renewal'), a:has-text('Services on DL'), button:has-text('Renewal')")
                    count = await dl_buttons.count()

                    if count > 0:
                        first_btn = dl_buttons.first
                        await first_btn.evaluate("el => el.style.outline = '3px solid #00c853'")
                        print(f"[Parivahan Co-Pilot] Identified {count} DL renewal navigation pathways on page.")

                    print("\n=======================================================")
                    print(" HUMAN HANDOFF: PARIVAHAN SECURITY GATE")
                    print("=======================================================")
                    print("1. Select 'Apply for DL Renewal' or 'Services on DL' on the screen.")
                    print("2. Enter your Driving License Number and solve the government CAPTCHA.")
                    print("3. The agent is standing by to assist with document upload and details.\n")

                    if not non_interactive:
                        # Keep window open for citizen interaction
                        await asyncio.to_thread(input, ">> Press [ENTER] when ready to finish session: ")
                        print("[Parivahan Co-Pilot] Wrapping up session...")
                    else:
                        await asyncio.sleep(3)

                except Exception as e:
                    print(f"[Parivahan Co-Pilot] Notice: {e}")
                finally:
                    await browser.close()
                    print("[Parivahan Co-Pilot] Browser session closed.")
        except Exception as e:
            print(f"[Parivahan Co-Pilot] Browser initialization notice: {e}")
            print(f"[Parivahan Co-Pilot] Direct portal URL: {self.PARIVAHAN_URL}")
