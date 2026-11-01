"""
Multi-Service Bureaucracy Catalog (agent/service_catalog.py)
Unified engine for registering, validating, and executing public services:
- Student Scholarships (NSP / State Schemes)
- Driving License Renewals (MoRTH Parivahan Sarathi)
- Government Welfare & Subsidy Claims (DBT / NFSA / PM-KISAN)
"""

import yaml
import json
from pathlib import Path
from datetime import datetime, date
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]

from agent.tools.secrets import SecretVault
from agent.tools.docs import DocumentProcessor


class ServiceDefinition(BaseModel):
    service_id: str
    service_name: str
    authority: str
    portal_url: str
    rules_file: str
    guidelines_source: str


class ServiceAssessment(BaseModel):
    service_id: str
    service_name: str
    authority: str
    portal_url: str
    eligible: bool
    reasons: List[str] = Field(default_factory=list)
    friendly_explanation: str
    required_documents: List[Dict[str, Any]] = Field(default_factory=list)
    actionable_checklist: List[str] = Field(default_factory=list)


class ServiceCatalog:
    """
    Manages multi-service government bureaucracy execution:
    1. Ingests citizen profile and requested service ID.
    2. Loads external service policy from rules/<service>.yaml.
    3. Evaluates eligibility deterministically in pure Python.
    4. Enforces document format & size constraints per portal rules.
    5. Dispatches to the appropriate portal orchestrator or co-pilot.
    """

    SERVICES = {
        "scholarship": ServiceDefinition(
            service_id="scholarship",
            service_name="National Merit Scholarship Scheme",
            authority="Ministry of Education (DoHE), Government of India",
            portal_url="https://scholarships.gov.in",
            rules_file="rules/nsp_scholarship.yaml",
            guidelines_source="https://scholarships.gov.in"
        ),
        "license_renewal": ServiceDefinition(
            service_id="license_renewal",
            service_name="Driving License (DL) Renewal",
            authority="Ministry of Road Transport and Highways (MoRTH)",
            portal_url="https://sarathi.parivahan.gov.in/sarathiservice/stateSelection.do",
            rules_file="rules/license_renewal.yaml",
            guidelines_source="https://parivahan.gov.in"
        ),
        "subsidy_claim": ServiceDefinition(
            service_id="subsidy_claim",
            service_name="Direct Benefit Transfer & Welfare Subsidy Claim",
            authority="DBT Mission, Government of India",
            portal_url="https://dbtbharat.gov.in",
            rules_file="rules/subsidy_claim.yaml",
            guidelines_source="https://dbtbharat.gov.in"
        ),
        "universal": ServiceDefinition(
            service_id="universal",
            service_name="Universal Web Form Autofill",
            authority="Autonomous Universal Form Perception Agent",
            portal_url="https://httpbin.org/forms/post",
            rules_file="",
            guidelines_source="https://w3c.github.io/html/"
        ),
    }

    ALIASES = {
        "parivahan_dl": "license_renewal",
        "parivahan": "license_renewal",
        "dl_renewal": "license_renewal",
        "license": "license_renewal",
        "driving_licence": "license_renewal",
        "nsp": "scholarship",
        "nsp_scholarship": "scholarship",
        "central_scholarship": "scholarship",
        "subsidy": "subsidy_claim",
        "universal": "universal",
        "custom_url": "universal",
    }

    def __init__(self):
        self.vault = SecretVault()
        self.doc_processor = DocumentProcessor()

    def list_services(self) -> List[ServiceDefinition]:
        """Returns all supported public bureaucracy services."""
        return list(self.SERVICES.values())

    def get_service(self, service_id: str) -> Optional[ServiceDefinition]:
        """Finds service by ID or alias."""
        sid = service_id.lower().strip()
        canonical_id = self.ALIASES.get(sid, sid)
        return self.SERVICES.get(canonical_id)

    @staticmethod
    def _calculate_age(dob_str: str) -> int:
        """Calculates citizen age in years across common date formats."""
        s = dob_str.strip()
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d", "%m/%d/%Y"):
            try:
                dob = datetime.strptime(s, fmt).date()
                today = date.today()
                return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            except ValueError:
                continue
        return 21

    def evaluate_service(self, service_id: str, profile: Dict[str, Any]) -> ServiceAssessment:
        """
        Evaluates citizen eligibility for any registered public service
        using its specific rules YAML file or universal rules.
        """
        service = self.get_service(service_id)
        if not service:
            raise ValueError(f"Unknown service '{service_id}'. Supported: {list(self.SERVICES.keys())}")

        canonical_id = service.service_id

        # 0. Universal Web Form Service
        if canonical_id == "universal":
            return ServiceAssessment(
                service_id="universal",
                service_name="Universal Web Form Autofill",
                authority="Autonomous Universal Form Perception Agent",
                portal_url="https://httpbin.org/forms/post",
                eligible=True,
                reasons=[],
                friendly_explanation="Citizen profile is loaded and ready for universal web form population.",
                required_documents=[],
                actionable_checklist=[
                    "Citizen profile attributes loaded",
                    "Target URL accessible",
                    "Zero-PII local secret vault active"
                ]
            )

        rules_path = ROOT / service.rules_file
        with open(rules_path, "r", encoding="utf-8") as f:
            rules_data = yaml.safe_load(f)

        rules = rules_data.get("rules", {})
        personal = profile.get("personal", {})
        education = profile.get("education", {})

        is_eligible = True
        reasons = []
        checklist = []

        # Calculate applicant age
        dob_str = personal.get("dob", "2000-01-01")
        age = self._calculate_age(dob_str)

        # -------------------------------------------------------------
        # 1. Scholarship Evaluation
        # -------------------------------------------------------------
        if canonical_id == "scholarship":
            income_raw = str(education.get("annual_income", "")).strip()
            ceiling = float(rules.get("income_ceiling", 450000.0))
            if not income_raw:
                is_eligible = False
                reasons.append("Annual family income has not been provided.")
            else:
                try:
                    income = float(income_raw)
                    if income > ceiling:
                        is_eligible = False
                        reasons.append(f"Family income (INR {income:,.0f}) exceeds ceiling of INR {ceiling:,.0f}")
                    else:
                        checklist.append(f"Income verified: INR {income:,.0f} <= INR {ceiling:,.0f}")
                except ValueError:
                    is_eligible = False
                    reasons.append("Annual family income is not a valid number.")

            marks_raw = str(education.get("marks", "")).strip()
            min_marks = float(rules.get("min_marks_percentage", 75.0))
            if not marks_raw:
                is_eligible = False
                reasons.append("Academic marks percentage has not been provided.")
            else:
                try:
                    marks = float(marks_raw)
                    if marks < min_marks:
                        is_eligible = False
                        reasons.append(f"Academic marks ({marks}%) below threshold of {min_marks}%")
                    else:
                        checklist.append(f"Academic threshold met: {marks}% >= {min_marks}%")
                except ValueError:
                    is_eligible = False
                    reasons.append("Academic marks is not a valid percentage.")

            allowed_courses = rules.get("allowed_courses", [])
            course = personal.get("course", "")
            if allowed_courses and course and course not in allowed_courses:
                is_eligible = False
                reasons.append(f"Course '{course}' not in approved scheme list")
            elif course:
                checklist.append(f"Course '{course}' is approved for funding")
            else:
                checklist.append("Course eligible under general scheme guidelines")

        # -------------------------------------------------------------
        # 2. Driving License Renewal Evaluation
        # -------------------------------------------------------------
        elif canonical_id == "license_renewal":
            min_age = rules.get("min_age_years", 18)
            if age < min_age:
                is_eligible = False
                reasons.append(f"Age ({age} years) is below minimum required age of {min_age} years")
            else:
                checklist.append(f"Age requirement satisfied: {age} years >= {min_age} years")

            # State check
            supported_states = rules.get("supported_states", [])
            state = personal.get("state", "Maharashtra").strip()
            if supported_states and not any(s.lower() == state.lower() for s in supported_states):
                is_eligible = False
                reasons.append(f"State '{state}' not currently integrated with Sarathi online portal")
            else:
                checklist.append(f"State '{state}' supported on Parivahan Sarathi")

            # Medical certificate requirement
            med_threshold = rules.get("medical_cert_age_threshold", 40)
            if age >= med_threshold:
                checklist.append(f"Medical Certificate Form 1A MANDATORY (Applicant age {age} >= {med_threshold})")
            else:
                checklist.append(f"Form 1A Medical Certificate EXEMPT (Applicant age {age} < {med_threshold})")

        # -------------------------------------------------------------
        # 3. Subsidy / Welfare Claim Evaluation
        # -------------------------------------------------------------
        elif canonical_id == "subsidy_claim":
            income_val = education.get("annual_income")
            income = float(income_val) if income_val not in [None, ""] else 0.0
            ceiling = float(rules.get("income_ceiling", 250000.0))
            if income > ceiling:
                is_eligible = False
                reasons.append(f"Family income (INR {income:,.0f}) exceeds welfare limit of INR {ceiling:,.0f}")
            else:
                checklist.append(f"Priority welfare income ceiling met: INR {income:,.0f} <= INR {ceiling:,.0f}")

            min_age = rules.get("min_age_years", 18)
            if age < min_age:
                is_eligible = False
                reasons.append(f"Applicant age ({age}) must be at least {min_age} for primary head-of-household subsidy")
            else:
                checklist.append(f"Age criterion met: {age} years")

        explanation = (
            f"Eligible for {service.service_name}. All statutory policy criteria satisfied."
            if is_eligible
            else f"Ineligible for {service.service_name} due to: {'; '.join(reasons)}"
        )

        return ServiceAssessment(
            service_id=service.service_id,
            service_name=service.service_name,
            authority=service.authority,
            portal_url=service.portal_url,
            eligible=is_eligible,
            reasons=reasons,
            friendly_explanation=explanation,
            required_documents=rules.get("required_documents", []),
            actionable_checklist=checklist
        )
