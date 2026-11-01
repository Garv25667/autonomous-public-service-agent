"""
Entity Extractor (agent/tools/entity_extractor.py)
Extracts structured citizen attributes (DL Number, Name, DOB, Income, Marks, College, State, etc.)
from uploaded PDFs, images, text transcripts, and conversational user messages.
"""

import io
import re
import json
import base64
from typing import Dict, Any, Optional, List
from pathlib import Path

import pypdf

INDIAN_STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh",
    "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka",
    "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram",
    "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu",
    "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal",
    "Andaman and Nicobar", "Chandigarh", "Dadra and Nagar Haveli", "Daman and Diu",
    "Delhi", "Jammu and Kashmir", "Ladakh", "Lakshadweep", "Puducherry"
]


class EntityExtractor:
    """
    Intelligent citizen entity extractor.
    Combines high-precision regex heuristic parsing with zero-token local execution.
    Can ingest raw PDF bytes, text documents, or natural language user prompts.
    """

    def extract_from_pdf_bytes(self, pdf_bytes: bytes) -> Dict[str, Any]:
        """Reads all extractable text from a PDF in-memory and parses entities."""
        try:
            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
            full_text = []
            for page in reader.pages:
                txt = page.extract_text()
                if txt:
                    full_text.append(txt)
            raw_text = "\n".join(full_text).strip()
            return self.extract_from_text(raw_text)
        except Exception as e:
            return {"error": f"Failed to extract PDF text: {str(e)}"}

    def extract_from_base64(self, b64_string: str, filename: Optional[str] = None) -> Dict[str, Any]:
        """Decodes base64 payload and parses entities."""
        # Strip data URL prefix if present (e.g. data:application/pdf;base64,...)
        if "," in b64_string:
            b64_string = b64_string.split(",", 1)[1]

        data = base64.b64decode(b64_string)
        if filename and filename.lower().endswith(".txt"):
            return self.extract_from_text(data.decode("utf-8", errors="ignore"))
        
        # Default assume PDF
        return self.extract_from_pdf_bytes(data)

    def extract_from_text(self, text: str) -> Dict[str, Any]:
        """
        Parses structured citizen attributes from freeform or document text.
        """
        entities: Dict[str, Any] = {}
        raw = text.strip()
        entities["raw_text_snippet"] = raw[:300] if len(raw) > 300 else raw

        # 1. Driving License Number
        # Standard formats: DL-0420110012345, MH1220190012345, RJ-14 2011 0012345, etc.
        dl_match = re.search(
            r'\b([A-Z]{2}[-\s]?[0-9]{2}[-\s]?[0-9]{4}[-\s]?[0-9]{7}|[A-Z]{2}[0-9]{2}[0-9]{11}|[A-Z]{2}[-\s]?[0-9]{13,15})\b',
            raw
        )
        if dl_match:
            entities["dl_number"] = re.sub(r'[-\s]', '', dl_match.group(1).upper())

        # 1b. Aadhaar Number (12 digits)
        aadhar_match = re.search(
            r'(?:Aadhaar|Aadhar|UID|UIDAI)[:\s]*([0-9]{4}[-\s]?[0-9]{4}[-\s]?[0-9]{4})\b|\b([2-9][0-9]{3}[-\s]?[0-9]{4}[-\s]?[0-9]{4})\b',
            raw,
            re.IGNORECASE
        )
        if aadhar_match:
            a_val = aadhar_match.group(1) or aadhar_match.group(2)
            if a_val:
                entities["aadhar_number"] = re.sub(r'[-\s]', '', a_val)

        # 2. Date of Birth (DOB)
        dob_match = re.search(
            r'(?:DOB|Date of Birth|Birth Date|D\.O\.B\.)[:\s]*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{4})',
            raw,
            re.IGNORECASE
        )
        if not dob_match:
            # Standalone date pattern (1950-2025)
            dob_match = re.search(r'\b([0-9]{1,2}[/-][0-9]{1,2}[/-](?:19|20)[0-9]{2})\b', raw)

        if dob_match:
            raw_dob = dob_match.group(1)
            # Normalize to YYYY-MM-DD or keep standard DD/MM/YYYY
            entities["dob"] = raw_dob

        # 3. Full Name
        name_match = re.search(
            r'(?:Holder(?:\'s)?\s*Name|Candidate Name|Applicant Name|Student Name|Citizen Name|Name)[:\s]*([A-Za-z\s\.\'-]+?)(?=\n|\r|,|S/O|D/O|DOB|Father|$)',
            raw,
            re.IGNORECASE
        )
        if name_match:
            cand = name_match.group(1).strip()
            cand = re.sub(r'^(?:is|am|are|was)\s+', '', cand, flags=re.IGNORECASE).strip()
            # Clean up trailing words
            if len(cand) >= 3 and not any(w in cand.lower() for w in ["college", "school", "department", "government", "licence"]):
                entities["full_name"] = cand

        # 4. Father's Name / Guardian
        father_match = re.search(
            r'(?:Father(?:\'s)?\s*Name|Father|S/O|D/O|W/O)[:\s]*([A-Za-z\s\.\'-]+?)(?=\n|\r|,|DOB|Address|$)',
            raw,
            re.IGNORECASE
        )
        if father_match:
            entities["father_name"] = father_match.group(1).strip()

        # 5. Annual Income
        income_match = re.search(
            r'(?:Annual\s*Income|Family\s*Income|Gross\s*Income|Income)[:\s]*(?:INR|Rs\.?|₹)?\s*([0-9,]{4,10})',
            raw,
            re.IGNORECASE
        )
        if income_match:
            entities["annual_income"] = income_match.group(1).replace(",", "").strip()

        # 6. Academic Marks / Percentage / GPA
        marks_match = re.search(
            r'(?:Percentage|Marks|Score|Aggregate|Percent)[:\s]*([0-9]{1,2}(?:\.[0-9]{1,2})?)\s*%?',
            raw,
            re.IGNORECASE
        )
        if not marks_match:
            marks_match = re.search(r'\b([0-9]{2}(?:\.[0-9]{1,2})?)\s*%', raw)
        if marks_match:
            entities["marks"] = marks_match.group(1).strip()

        # 7. College / Institution
        college_match = re.search(
            r'(?:College|Institution|University|Institute)[:\s]*([^\n\r]+)',
            raw,
            re.IGNORECASE
        )
        if college_match:
            entities["college"] = college_match.group(1).strip()

        # 8. Course / Program
        course_match = re.search(
            r'(?:Course|Degree|Program|Branch)[:\s]*([^\n\r]+)',
            raw,
            re.IGNORECASE
        )
        if not course_match:
            # Inline course matching
            inline_course = re.search(r'\b(B\.?Tech|B\.?E\.?|B\.?Sc|B\.?Com|B\.?A\.?|Diploma|M\.?Tech|MBA|MBBS)\b', raw, re.I)
            if inline_course:
                entities["course"] = inline_course.group(1)
        else:
            entities["course"] = course_match.group(1).strip()

        # 9. Category (General, OBC, SC, ST, EWS)
        cat_match = re.search(r'\b(General|OBC|SC|ST|EWS)\b', raw, re.IGNORECASE)
        if cat_match:
            entities["category"] = cat_match.group(1).upper() if cat_match.group(1).upper() in ["SC", "ST", "OBC", "EWS"] else "General"

        # 10. Indian State
        for st in INDIAN_STATES:
            if re.search(rf'\b{re.escape(st)}\b', raw, re.IGNORECASE):
                entities["state"] = st
                break

        # 11. Phone Number (10 digits)
        phone_match = re.search(r'\b([6-9][0-9]{9})\b', raw)
        if phone_match:
            entities["phone"] = phone_match.group(1)

        # 12. Email
        email_match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', raw)
        if email_match:
            entities["email"] = email_match.group(0)

        # 13. Address
        addr_match = re.search(r'(?:Address|Permanent Address)[:\s]*([^\n\r]+)', raw, re.IGNORECASE)
        if addr_match:
            entities["address"] = addr_match.group(1).strip()

        return entities

    def update_citizen_profile(
        self,
        extracted: Dict[str, Any],
        profile_path: Optional[Path] = None
    ) -> Dict[str, Any]:
        """
        Merges extracted entities into data/citizen.json safely.
        """
        target = profile_path or (Path(__file__).resolve().parents[2] / "data" / "citizen.json")
        data: Dict[str, Any] = {"personal": {}, "education": {}, "license": {}}

        if target.exists():
            with open(target, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                except Exception:
                    data = {"personal": {}, "education": {}, "license": {}}

        if "personal" not in data:
            data["personal"] = {}
        if "education" not in data:
            data["education"] = {}
        if "license" not in data:
            data["license"] = {}

        # Merge personal
        if "full_name" in extracted:
            data["personal"]["full_name"] = extracted["full_name"]
        if "dob" in extracted:
            data["personal"]["dob"] = extracted["dob"]
        if "category" in extracted:
            data["personal"]["category"] = extracted["category"]
        if "course" in extracted:
            data["personal"]["course"] = extracted["course"]
        if "state" in extracted:
            data["personal"]["state"] = extracted["state"]
        if "address" in extracted:
            data["personal"]["address"] = extracted["address"]
        if "father_name" in extracted:
            data["personal"]["father_name"] = extracted["father_name"]
        if "aadhar_number" in extracted:
            data["personal"]["aadhar_number"] = extracted["aadhar_number"]

        # Merge education
        if "college" in extracted:
            data["education"]["college"] = extracted["college"]
        if "marks" in extracted:
            data["education"]["marks"] = str(extracted["marks"])
        if "annual_income" in extracted:
            data["education"]["annual_income"] = str(extracted["annual_income"])

        # Merge license
        if "dl_number" in extracted:
            data["license"]["dl_number"] = extracted["dl_number"]
            data["personal"]["dl_number"] = extracted["dl_number"]

        with open(target, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        return data
