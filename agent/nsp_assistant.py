"""
Live NSP Co-Pilot & Assistant (agent/nsp_assistant.py)
Provides assisted form-filling, document pre-validation (<= 200 KB),
and human-in-the-loop navigation for the real National Scholarship Portal (scholarships.gov.in).
"""

import sys
import time
import json
import yaml
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]

from agent.eligibility import EligibilityResult
from agent.tools.docs import DocumentProcessor, DocumentValidationResult
from agent.tools.secrets import SecretVault
from agent.perception import SemanticMapper

try:
    from playwright.async_api import async_playwright, Page, Browser
except ImportError:
    pass


class NSPValidationSummary(BaseModel):
    """Pre-flight verification results for NSP."""
    eligible: bool
    scheme_name: str
    reasons: List[str] = Field(default_factory=list)
    document_valid: bool = False
    document_size_kb: float = 0.0
    document_message: str = ""
    sanitized_profile: Dict[str, Any] = Field(default_factory=dict)


class NSPAssistant:
    """
    Assisted Co-Pilot for the National Scholarship Portal (scholarships.gov.in):
    1. Evaluates official NSP eligibility guidelines from rules/nsp_scholarship.yaml.
    2. Validates document format and strict <= 200 KB NSP size limit.
    3. Tokenizes citizen PII to prevent leaks.
    4. Launches a visible browser to scholarships.gov.in and guides the user through OTR / login.
    5. Assists with field filling and enforces strict human approval before submission.
    """

    def __init__(self, rules_path: Optional[Path] = None, profile_path: Optional[Path] = None):
        self.rules_path = rules_path or (ROOT / "rules" / "nsp_scholarship.yaml")
        self.profile_path = profile_path or (ROOT / "data" / "citizen.json")
        self.rules = self._load_rules()
        self.profile = self._load_profile()

        self.vault = SecretVault()
        self.doc_processor = DocumentProcessor()
        self.mapper = SemanticMapper()

    def _load_rules(self) -> Dict[str, Any]:
        with open(self.rules_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _load_profile(self) -> Dict[str, Any]:
        with open(self.profile_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def check_nsp_eligibility(self) -> EligibilityResult:
        """Evaluates citizen data against published Central Sector Scheme criteria."""
        personal = self.profile.get("personal", {})
        education = self.profile.get("education", {})
        rules_cfg = self.rules.get("rules", {})

        reasons = []
        is_eligible = True

        # 1. Income Ceiling (NSP CSSS: <= 4,50,000)
        income_val = education.get("annual_income")
        income = float(income_val) if income_val not in [None, ""] else 0.0
        income_ceiling = float(rules_cfg.get("income_ceiling", 450000.0))
        if income > income_ceiling:
            is_eligible = False
            reasons.append(f"Annual family income (INR {income:,.0f}) exceeds NSP limit of INR {income_ceiling:,.0f}")

        # 2. Minimum Academic Marks (NSP CSSS: >= 75%)
        marks_val = education.get("marks")
        marks = float(marks_val) if marks_val not in [None, ""] else 0.0
        min_marks = float(rules_cfg.get("min_marks_percentage", 75.0))
        if marks < min_marks:
            is_eligible = False
            reasons.append(f"Previous exam percentage ({marks}%) is below NSP requirement of {min_marks}%")

        # 3. Approved Courses
        course = personal.get("course", "")
        allowed_courses = rules_cfg.get("allowed_courses", [])
        if allowed_courses and course not in allowed_courses:
            is_eligible = False
            reasons.append(f"Course '{course}' is not in approved list: {', '.join(allowed_courses[:5])}...")

        scheme_title = self.rules.get("scheme_name", "National Scholarship Scheme")
        if is_eligible:
            explanation = f"Eligible for {scheme_title}. Income within limit and marks exceed merit cut-off."
        else:
            explanation = f"Ineligible for {scheme_title} due to: {'; '.join(reasons)}"

        return EligibilityResult(
            eligible=is_eligible,
            reasons=reasons,
            friendly_explanation=explanation
        )

    def validate_nsp_document(self, file_path: Optional[Path] = None) -> Tuple[bool, float, str]:
        """
        Validates document against real NSP constraints:
        - Must be .pdf, .jpg, or .jpeg
        - Maximum size: exactly 200 KB
        """
        if file_path is None:
            file_path = ROOT / self.profile.get("education", {}).get("marksheet_path", "")

        if not file_path.exists():
            return False, 0.0, f"Document file not found at: {file_path}"

        size_kb = file_path.stat().st_size / 1024.0
        ext = file_path.suffix.lower()

        if ext not in [".pdf", ".jpg", ".jpeg"]:
            return False, size_kb, f"Invalid format '{ext}'. Real NSP accepts only PDF or JPG."

        # Real NSP constraint: <= 200 KB
        if size_kb > 200.0:
            return False, size_kb, f"File size {size_kb:.1f} KB exceeds real NSP 200 KB limit. Compression required."

        return True, size_kb, f"Document passes real NSP size constraint ({size_kb:.1f} KB <= 200 KB)."

    def run_preflight_audit(self) -> NSPValidationSummary:
        """Executes full pre-flight verification before launching the live portal."""
        eligibility = self.check_nsp_eligibility()
        doc_valid, doc_kb, doc_msg = self.validate_nsp_document()
        scheme_title = self.rules.get("scheme_name", "National Scholarship Scheme")

        # Tokenize PII
        self.vault.load_from_profile(self.profile)
        sanitized = self.vault.mask_profile(self.profile)

        return NSPValidationSummary(
            eligible=eligibility.eligible,
            scheme_name=scheme_title,
            reasons=eligibility.reasons,
            document_valid=doc_valid,
            document_size_kb=round(doc_kb, 1),
            document_message=doc_msg,
            sanitized_profile=sanitized
        )

    async def launch_assisted_session(self, target_url: str = "https://scholarships.gov.in"):
        """
        Launches an interactive, visible Playwright browser session directed at scholarships.gov.in.
        Functions strictly as an assisted Co-Pilot:
        - Pauses at CAPTCHA / Aadhaar OTR login.
        - Provides field assistance.
        - Enforces strict human approval before submission.
        """
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False, slow_mo=500)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            try:
                print(f"\n[NSP Co-Pilot] Navigating to official portal: {target_url}...")
                await page.goto(target_url, timeout=30000)
                await page.wait_for_load_state("domcontentloaded")

                print("[NSP Co-Pilot] Portal loaded successfully.")
                print("[NSP Co-Pilot] HUMAN HANDOFF: Please review portal notices, solve any visual CAPTCHAs,")
                print("               or navigate to your applicant dashboard in the open browser window.")
                print("\nPress Enter in this terminal once you are on your desired application form page...")
                
                # Wait for user acknowledgment in terminal
                await asyncio.to_thread(input, ">> Press [ENTER] to continue assisted field mapping: ")

                print("[NSP Co-Pilot] Reading page structure and form inputs...")
                content = await page.content()
                
                # Check for active input fields
                inputs = await page.locator("input, select").all()
                print(f"[NSP Co-Pilot] Detected {len(inputs)} interactive form elements.")
                print("[NSP Co-Pilot] Assisted mode ready. Citizen retains full submission control.")

                print("\nKeeping session open for 30 seconds for your review...")
                await asyncio.sleep(30)

            except Exception as e:
                print(f"[NSP Co-Pilot] Session notice: {str(e)}")
            finally:
                await browser.close()
                print("[NSP Co-Pilot] Browser session closed.")
