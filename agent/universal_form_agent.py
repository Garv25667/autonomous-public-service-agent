"""
Universal Form Agent (agent/universal_form_agent.py)
A generalized autonomous agent that can navigate to ANY live public web page,
semantically identify form fields, and fill them with citizen data in visible slow-mo.
"""

import sys
import re
import json
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, List

ROOT = Path(__file__).resolve().parents[1]

try:
    from playwright.async_api import async_playwright, Page, Locator
except ImportError:
    pass


class UniversalFormAgent:
    """
    Autonomously analyzes and fills any real, external HTML form:
    1. Reads accessibility labels, placeholders, names, and IDs.
    2. Maps citizen profile values using semantic fuzzy heuristics.
    3. Visually highlights each field with a blue outline as it types.
    4. Handles text, number, date, select dropdowns, textareas, and file uploads.
    """

    def __init__(self, profile_path: Optional[Path] = None, slow_mo_ms: int = 500, on_action_callback: Optional[Any] = None):
        self.profile_path = profile_path or (ROOT / "data" / "citizen.json")
        self.slow_mo_ms = slow_mo_ms
        self.on_action_callback = on_action_callback
        self.profile = self._load_profile()

    def _load_profile(self) -> Dict[str, Any]:
        data = {}
        if Path(self.profile_path).exists():
            with open(self.profile_path, "r", encoding="utf-8") as f:
                data = json.load(f)

        personal = data.get("personal", {})
        education = data.get("education", {})
        license_info = data.get("license", {})

        marksheet_raw = education.get("marksheet_path", "")
        marksheet_full = str(ROOT / marksheet_raw) if marksheet_raw else ""

        return {
            "full_name": personal.get("full_name", ""),
            "dob": personal.get("dob", ""),
            "dl_number": license_info.get("dl_number") or personal.get("dl_number", ""),
            "aadhar_number": personal.get("aadhar_number", ""),
            "application_id": personal.get("application_id", ""),
            "email": personal.get("email", ""),
            "phone": personal.get("phone", ""),
            "category": personal.get("category", "General"),
            "course": personal.get("course", "B.Tech"),
            "college": education.get("college", ""),
            "course_year": education.get("course_year", ""),
            "marks": str(education.get("marks", "")),
            "annual_income": str(education.get("annual_income", "")),
            "marksheet_path": marksheet_full,
            "state": personal.get("state", "Rajasthan"),
            "district": personal.get("district", "Ajmer"),
            "block": personal.get("block", "Ajmer"),
            "statement": f"Applicant {personal.get('full_name', '')} applying for public service benefit."
        }

    def _classify_field_intent(self, label_text: str) -> Optional[str]:
        """Classifies an element's label/placeholder into a profile attribute."""
        txt = label_text.lower().strip()

        # Name
        if any(w in txt for w in ["full name", "applicant name", "student name", "candidate name", "fullname", "your name", "custname"]):
            return "full_name"
        if txt in ["name", "fname", "first name"] and not any(w in txt for w in ["college", "school", "inst", "father", "mother"]):
            return "full_name"

        # Driving Licence Number
        if any(w in txt for w in ["driving licence", "driving license", "dl number", "dl no", "licence no", "license no", "dlno", "licencenumber", "licensenumber"]):
            return "dl_number"
        if txt in ["dl", "licence", "license"] and not any(w in txt for w in ["type", "class", "issue", "state", "menu"]):
            return "dl_number"

        # Aadhaar / National ID
        if any(w in txt for w in ["aadhaar", "aadhar", "uid", "national id", "identity number"]):
            return "aadhar_number"

        # Application / User ID
        if any(w in txt for w in ["application id", "application no", "reg id", "registration id", "user id", "username", "login id"]):
            return "application_id"

        # Human challenge fields
        if any(w in txt for w in ["captcha", "security code", "code shown"]):
            return "captcha"
        if any(w in txt for w in ["password", "passcode"]):
            return "password"
        if any(w in txt for w in ["otp", "one time password"]):
            return "otp"

        # Email
        if any(w in txt for w in ["email", "e-mail", "mail address", "custemail"]):
            return "email"

        # Phone
        if any(w in txt for w in ["phone", "mobile", "telephone", "contact number", "tel", "custtel"]):
            return "phone"

        # Date of Birth
        if any(w in txt for w in ["date of birth", "dob", "birth date", "birthdate"]):
            return "dob"

        # Income
        if any(w in txt for w in ["income", "annual income", "family income", "salary"]):
            return "annual_income"

        # Document upload (check before marks because "marksheet" contains "marks")
        if any(w in txt for w in ["marksheet", "transcript", "document", "upload", "file", "certificate"]):
            return "marksheet_path"

        # Marks / GPA
        if any(w in txt for w in ["marks", "percentage", "gpa", "grade", "score", "percent"]):
            return "marks"

        # College / Institution
        if any(w in txt for w in ["college", "institution", "school", "university", "institute", "attended"]):
            return "college"

        # Course / Major
        if any(w in txt for w in ["course", "degree", "major", "program", "field of study", "branch"]):
            return "course"

        # Year
        if any(w in txt for w in ["current year", "course year", "academic year", "gradyear", "graduation year"]):
            return "course_year"

        # Category
        if any(w in txt for w in ["category", "caste", "quota", "community"]):
            return "category"

        # Statement / Essay / Purpose (check before 'state' because 'statement' contains 'state')
        if any(w in txt for w in ["statement", "essay", "purpose", "why", "comments", "description"]):
            return "statement"

        # State / Location
        if re.search(r"\bstate\b", txt) or "province" in txt:
            return "state"
        if any(w in txt for w in ["district", "city"]):
            return "district"
        if any(w in txt for w in ["block", "taluka", "subdistrict"]):
            return "block"

        return None

    async def fill_page(self, page: Page, dry_run: bool = True) -> int:
        """
        Inspects the loaded page, detects all fields, highlights them, and fills them.
        Returns total number of fields filled.
        """
        print("\n[Agent] Scanning page DOM for interactive form elements...")

        # Extract all candidate form fields and their metadata in one efficient browser eval
        fields_meta = await page.evaluate("""() => {
            const elements = Array.from(document.querySelectorAll('input, select, textarea'));
            return elements.map((el, idx) => {
                // Find label text
                let label = '';
                if (el.labels && el.labels.length > 0) {
                    label = el.labels[0].innerText;
                }
                if (!label && el.id) {
                    const l = document.querySelector('label[for="' + el.id + '"]');
                    if (l) label = l.innerText;
                }
                if (!label) {
                    label = el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.name || el.id || '';
                }
                
                return {
                    idx: idx,
                    tag: el.tagName.toLowerCase(),
                    type: (el.type || 'text').toLowerCase(),
                    name: el.name || '',
                    id: el.id || '',
                    placeholder: el.getAttribute('placeholder') || '',
                    label: label.trim(),
                    visible: el.offsetParent !== null && !el.disabled && el.type !== 'hidden'
                };
            }).filter(f => f.visible);
        }""")

        print(f"[Agent] Found {len(fields_meta)} visible interactive elements on page.\n")
        filled_count = 0

        for f in fields_meta:
            tag = f.get("tag", "")
            ftype = f.get("type", "text")
            label = f.get("label", "")
            idx = f.get("idx", 0)
            placeholder = f.get("placeholder", "")
            name = f.get("name", "")
            el_id = f.get("id", "")

            # Auto-check consent / terms / privacy policy checkboxes
            if ftype == "checkbox":
                comb = f"{label} {placeholder} {name} {el_id}".lower()
                if any(w in comb for w in ["privacy", "terms", "agree", "accept", "declare", "declaration", "consent"]):
                    try:
                        el_locator = page.locator(f"#{el_id}").first if el_id else page.locator("input[type='checkbox']").nth(idx)
                        if await el_locator.is_visible():
                            await el_locator.evaluate("el => el.style.outline = '3px solid #00c853'")
                            await el_locator.check()
                            filled_count += 1
                            print(f"  -> Checked consent checkbox: [{label[:30]}...]")
                    except Exception:
                        pass
                    continue

            # Match label, placeholder, name, or id to profile field
            intent = self._classify_field_intent(label)
            if not intent and placeholder:
                intent = self._classify_field_intent(placeholder)
            if not intent and name:
                intent = self._classify_field_intent(name)
            if not intent and el_id:
                intent = self._classify_field_intent(el_id)

            if not intent:
                continue

            value = self.profile.get(intent)
            if not value:
                continue

            # Auto-format DOB if field asks for DD-MM-YYYY or DD/MM/YYYY
            if intent == "dob" and value:
                m_dob = re.match(r'^(\d{4})[-/](\d{2})[-/](\d{2})$', str(value).strip())
                if m_dob:
                    delim = "-" if "-" in placeholder or "-" in label else ("/" if "/" in placeholder or "/" in label else "-")
                    value = f"{m_dob.group(3)}{delim}{m_dob.group(2)}{delim}{m_dob.group(1)}"

            try:
                # Target the element cleanly by id, name, or DOM index
                if el_id:
                    el_locator = page.locator(f"#{el_id}").first
                elif name:
                    el_locator = page.locator(f"{tag}[name='{name}']").first
                else:
                    el_locator = page.locator("input, select, textarea").nth(idx)

                if not await el_locator.is_visible():
                    continue

                # Visual highlight (glowing cyan outline) so the user sees the agent's focus!
                await el_locator.evaluate("el => el.style.outline = '3px solid #00c853'")

                if tag == "select":
                    # Dropdown selection
                    print(f"  -> Selecting [{label or intent}]: '{value}'")
                    # Try selecting by label, then value, then index
                    try:
                        await el_locator.select_option(label=value, timeout=2000)
                    except Exception:
                        try:
                            await el_locator.select_option(value=value, timeout=2000)
                        except Exception:
                            # Select first non-empty option
                            await el_locator.select_option(index=1, timeout=2000)
                    filled_count += 1

                elif tag == "textarea":
                    print(f"  -> Filling [{label or intent}]: '{value[:30]}...'")
                    await el_locator.fill(value)
                    filled_count += 1

                elif ftype == "file":
                    print(f"  -> Uploading [{label or intent}]: '{Path(value).name}'")
                    await el_locator.set_input_files(value)
                    filled_count += 1

                elif ftype in ["checkbox", "radio"]:
                    print(f"  -> Checking [{label or intent}]")
                    await el_locator.check()
                    filled_count += 1

                elif ftype not in ["submit", "button", "reset"]:
                    # Text / number / date / email input
                    print(f"  -> Typing [{label or intent}]: '{value}'")
                    await el_locator.fill(value)
                    filled_count += 1

                await asyncio.sleep(0.15)
                if self.on_action_callback:
                    try:
                        res = self.on_action_callback(page, f"Autofilled {label or intent}: {value}", "FIELD_FILL")
                        if asyncio.iscoroutine(res):
                            await res
                    except Exception:
                        pass

            except Exception as e:
                # Non-fatal field skip
                continue

        print(f"\n[Agent] Successfully filled {filled_count} fields across the form!")
        return filled_count

    async def inspect_url(self, url: str) -> Dict[str, Any]:
        """
        Navigates to the real URL, extracts visible interactive fields,
        checks which fields the citizen has ready, which are missing,
        and identifies any human challenges (CAPTCHA, password, OTP).
        """
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            try:
                await page.goto(url, timeout=7000, wait_until="domcontentloaded")
                try:
                    await page.wait_for_load_state("networkidle", timeout=3000)
                except Exception:
                    await page.wait_for_timeout(1000)

                title = await page.title()

                fields_meta = await page.evaluate("""() => {
                    const elements = Array.from(document.querySelectorAll('input, select, textarea'));
                    return elements.map((el, idx) => {
                        let label = '';
                        if (el.labels && el.labels.length > 0) label = el.labels[0].innerText;
                        if (!label && el.id) {
                            const l = document.querySelector('label[for="' + el.id + '"]');
                            if (l) label = l.innerText;
                        }
                        if (!label) {
                            label = el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.name || el.id || '';
                        }
                        let rect = el.getBoundingClientRect();
                        let style = window.getComputedStyle(el);
                        let visible = style.display !== 'none' && style.visibility !== 'hidden' && !el.disabled && el.type !== 'hidden';
                        return {
                            idx: idx,
                            tag: el.tagName.toLowerCase(),
                            type: (el.type || 'text').toLowerCase(),
                            name: el.name || '',
                            id: el.id || '',
                            placeholder: el.getAttribute('placeholder') || '',
                            ariaLabel: el.getAttribute('aria-label') || '',
                            label: label.trim(),
                            visible: visible
                        };
                    }).filter(f => f.visible);
                }""")

                ready_fields = []
                missing_fields = []
                human_gates = []
                seen_intents = set()

                for f in fields_meta:
                    label = f.get("label") or f.get("placeholder") or f.get("name") or "Field"
                    ftype = f.get("type", "text")
                    placeholder = f.get("placeholder") or ""
                    comb = f"{label} {placeholder}".strip()
                    intent = self._classify_field_intent(comb)

                    if intent == "aadhar_number":
                        val = self.profile.get("aadhar_number")
                        if val:
                            if "aadhar_number" not in seen_intents:
                                ready_fields.append({"field": "Aadhaar Number", "intent": "aadhar_number", "value": val})
                                seen_intents.add("aadhar_number")
                        else:
                            if "aadhar_number" not in seen_intents:
                                missing_fields.append({"field": "Aadhaar Number", "intent": "aadhar_number"})
                                seen_intents.add("aadhar_number")
                    elif ftype == "password" or intent == "password":
                        human_gates.append(f"Password ({label})")
                    elif intent in ["captcha", "otp"] or ftype == "text" and any(w in comb.lower() for w in ["captcha", "otp"]):
                        human_gates.append(f"{intent.upper() if intent else 'VERIFICATION'} ({label})")
                    elif intent:
                        val = self.profile.get(intent)
                        if val:
                            if intent not in seen_intents:
                                ready_fields.append({"field": label, "intent": intent, "value": val})
                                seen_intents.add(intent)
                        else:
                            if intent not in seen_intents:
                                missing_fields.append({"field": label, "intent": intent})
                                seen_intents.add(intent)
                    else:
                        if label and label.lower() not in ["close", "submit", "button"] and len(label) > 2:
                            missing_fields.append({"field": label, "intent": "custom"})

                return {
                    "success": True,
                    "url": url,
                    "title": title or url,
                    "total_fields": len(fields_meta),
                    "ready_fields": ready_fields,
                    "missing_fields": missing_fields,
                    "human_gates": list(set(human_gates))
                }
            except Exception as e:
                return {
                    "success": False,
                    "url": url,
                    "error": str(e)
                }
            finally:
                await browser.close()
