import yaml
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from .llm.client import LLMClient


class EligibilityResult(BaseModel):
    """Result of deterministic evaluation against scholarship YAML rules."""
    eligible: bool
    reasons: List[str] = Field(default_factory=list)
    missing_docs: List[str] = Field(default_factory=list)
    friendly_explanation: Optional[str] = None


class EligibilityEvaluator:
    """
    Implements Feature F3: Eligibility Pre-Check from the 48-Hour Playbook:
    - Pure Python function evaluates YAML rules against citizen profile.
    - Zero LLM rule invention: The LLM does NOT invent eligibility rules.
    - Deterministic checks for income ceiling, marks minimum, age, category, and documents.
    """

    def __init__(self, rules_path: Optional[Path] = None, llm_client: Optional[LLMClient] = None):
        if rules_path is None:
            rules_path = Path(__file__).resolve().parents[1] / "rules" / "scholarship.yaml"
        self.rules_path = Path(rules_path)
        self.llm_client = llm_client
        self.rules = self._load_rules()

    def _load_rules(self) -> Dict[str, Any]:
        if not self.rules_path.exists():
            raise FileNotFoundError(f"Eligibility rules YAML not found at: {self.rules_path}")
        with open(self.rules_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    @staticmethod
    def _calculate_age(dob_str: str) -> int:
        """Calculates age in years from YYYY-MM-DD string."""
        dob = datetime.strptime(dob_str.strip(), "%Y-%m-%d").date()
        today = date.today()
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

    def evaluate(self, profile: Dict[str, Any]) -> EligibilityResult:
        """
        Evaluates citizen profile against configured rules.
        """
        rules = self.rules.get("rules", {})
        personal = profile.get("personal", {})
        education = profile.get("education", {})

        reasons = []
        missing_docs = []
        is_eligible = True

        # 1. Income Ceiling Check
        income_ceiling = rules.get("income_ceiling", 800000.0)
        try:
            income = float(education.get("annual_income", 0))
            if income > income_ceiling:
                is_eligible = False
                reasons.append(f"Annual income ₹{income:,.0f} exceeds ceiling of ₹{income_ceiling:,.0f}")
            else:
                reasons.append(f"Annual income ₹{income:,.0f} is within ceiling (₹{income_ceiling:,.0f})")
        except (ValueError, TypeError):
            is_eligible = False
            reasons.append("Invalid or missing annual income value.")

        # 2. Minimum Marks Percentage Check
        min_marks = rules.get("min_marks_percentage", 60.0)
        try:
            marks = float(education.get("marks", 0))
            if marks < min_marks:
                is_eligible = False
                reasons.append(f"Marks {marks:.1f}% are below minimum requirement of {min_marks:.1f}%")
            else:
                reasons.append(f"Marks {marks:.1f}% meet minimum requirement of {min_marks:.1f}%")
        except (ValueError, TypeError):
            is_eligible = False
            reasons.append("Invalid or missing previous examination marks.")

        # 3. Category Check
        allowed_cats = rules.get("allowed_categories", [])
        cat = personal.get("category", "")
        if cat not in allowed_cats:
            is_eligible = False
            reasons.append(f"Category '{cat}' is not in approved categories: {allowed_cats}")
        else:
            reasons.append(f"Category '{cat}' is approved")

        # 4. Course Check
        allowed_courses = rules.get("allowed_courses", [])
        course = personal.get("course", "")
        if course not in allowed_courses:
            is_eligible = False
            reasons.append(f"Course '{course}' is not in approved courses: {allowed_courses}")
        else:
            reasons.append(f"Course '{course}' is approved")

        # 5. Age Check
        max_age = rules.get("max_age_years", 26)
        dob = personal.get("dob")
        if dob:
            try:
                age = self._calculate_age(dob)
                if age > max_age:
                    is_eligible = False
                    reasons.append(f"Age {age} exceeds maximum age limit of {max_age} years")
                else:
                    reasons.append(f"Age {age} is within limit ({max_age} years)")
            except ValueError:
                is_eligible = False
                reasons.append(f"Invalid date of birth format '{dob}' (expected YYYY-MM-DD)")

        # 6. Required Documents Readiness Check
        required_docs = rules.get("required_documents", [])
        root_dir = Path(__file__).resolve().parents[1]
        for doc in required_docs:
            doc_name = doc.get("name")
            if doc_name == "marksheet":
                path_str = education.get("marksheet_path", "")
                if not path_str:
                    is_eligible = False
                    missing_docs.append("marksheet")
                    reasons.append("Marksheet file path not specified in profile.")
                else:
                    doc_file = root_dir / path_str
                    if not doc_file.exists():
                        is_eligible = False
                        missing_docs.append("marksheet")
                        reasons.append(f"Marksheet document file missing on disk: {doc_file}")
                    else:
                        reasons.append(f"Required document '{doc_name}' verified present on disk.")

        # Friendly explanation
        explanation = (
            f"Eligible for {self.rules.get('scheme_name', 'Scholarship')}. All criteria satisfied."
            if is_eligible
            else f"Ineligible for {self.rules.get('scheme_name', 'Scholarship')}. Issues: {'; '.join(reasons)}"
        )

        return EligibilityResult(
            eligible=is_eligible,
            reasons=reasons,
            missing_docs=missing_docs,
            friendly_explanation=explanation
        )
