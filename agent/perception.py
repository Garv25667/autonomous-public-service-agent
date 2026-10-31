import logging
from typing import List, Optional, Dict
from rapidfuzz import process, fuzz

from .llm.client import LLMClient
from .llm.schemas import DropdownMatch

logger = logging.getLogger(__name__)

# Common synonyms and variations for scholarship portal options
COMMON_SYNONYMS: Dict[str, List[str]] = {
    # Categories
    "General": ["GEN", "Open", "Unreserved", "General Category", "GEN-EWS"],
    "OBC": ["Other Backward Class", "OBC-NCL", "BC"],
    "SC": ["Scheduled Caste", "SC Category"],
    "ST": ["Scheduled Tribe", "ST Category"],

    # Courses
    "B.Tech": [
        "Bachelor of Technology", "B.E.", "Bachelor of Engineering",
        "Engineering", "BTech"
    ],
    "M.Tech": ["Master of Technology", "M.E.", "MTech"],
    "B.Sc": ["Bachelor of Science", "BSc"],
    "M.Sc": ["Master of Science", "MSc"],
    "B.Com": ["Bachelor of Commerce", "BCom"],
    "B.A.": ["Bachelor of Arts", "BA"],
    "MBA": ["Master of Business Administration"],

    # Course years
    "First Year": ["1st Year", "Year 1", "Freshman", "FE"],
    "Second Year": ["2nd Year", "Year 2", "Sophomore", "SE"],
    "Third Year": ["3rd Year", "Year 3", "Junior", "TE"],
    "Final Year": ["4th Year", "Year 4", "Senior", "BE", "Fourth Year"],
}


class SemanticMapper:
    """
    Implements Playbook Feature F2: Profile to form semantic mapping.
    Tiers:
    1. Exact Match (case-insensitive) -> confidence 1.0
    2. Synonym Lookup -> confidence 0.95
    3. Fuzzy Matching (rapidfuzz token_sort_ratio >= 80) -> confidence 0.80 - 0.94
    4. LLM Fallback (Gemini Flash-Lite structured JSON) -> model confidence
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        confidence_threshold: float = 0.75
    ):
        self.llm_client = llm_client
        self.confidence_threshold = confidence_threshold

    def match_dropdown(
        self,
        target_value: str,
        options: List[str],
        field_label: str = ""
    ) -> DropdownMatch:
        """
        Matches a profile attribute to one of the portal's dropdown options.
        Returns a DropdownMatch with choice, confidence, and evidence.
        """
        if not target_value or not options:
            return DropdownMatch(choice=None, confidence=0.0, evidence="Empty input or options")

        cleaned_target = target_value.strip()

        # --- Tier 1: Exact Match (case-insensitive) ---
        for opt in options:
            if opt.strip().lower() == cleaned_target.lower():
                return DropdownMatch(
                    choice=opt,
                    confidence=1.0,
                    evidence=f"Tier 1 exact match on '{opt}'"
                )

        # --- Tier 2: Synonym Table Match ---
        # 2a. Target value has known synonyms
        synonyms = COMMON_SYNONYMS.get(cleaned_target, [])
        for opt in options:
            clean_opt = opt.strip().lower()
            for syn in synonyms:
                if syn.lower() == clean_opt:
                    return DropdownMatch(
                        choice=opt,
                        confidence=0.95,
                        evidence=f"Tier 2 synonym match: '{cleaned_target}' -> '{opt}'"
                    )

        # 2b. Check if any option has synonyms matching the target
        for opt in options:
            clean_opt = opt.strip()
            if clean_opt in COMMON_SYNONYMS:
                for syn in COMMON_SYNONYMS[clean_opt]:
                    if syn.lower() == cleaned_target.lower():
                        return DropdownMatch(
                            choice=opt,
                            confidence=0.95,
                            evidence=f"Tier 2 reverse synonym match: '{cleaned_target}' -> '{opt}'"
                        )

        # --- Tier 3: Fuzzy Match via rapidfuzz ---
        match = process.extractOne(
            cleaned_target,
            options,
            scorer=fuzz.token_sort_ratio
        )
        if match:
            best_opt, score, _ = match
            if score >= 80:
                confidence = round(score / 100.0, 2)
                return DropdownMatch(
                    choice=best_opt,
                    confidence=confidence,
                    evidence=f"Tier 3 fuzzy match with token sort ratio {score}%"
                )

        # --- Tier 4: LLM Fallback (Gemini Flash-Lite structured JSON) ---
        if self.llm_client:
            prompt = (
                f"You are matching a citizen's profile data to the closest valid option in a government scholarship form.\n"
                f"Form Field: '{field_label}'\n"
                f"Citizen Profile Value: '{cleaned_target}'\n"
                f"Available Dropdown Options: {options}\n\n"
                f"Instructions:\n"
                f"1. Select the exact option from the list that matches the citizen value.\n"
                f"2. Provide your confidence score between 0.0 and 1.0.\n"
                f"3. State your brief evidence/reasoning.\n"
                f"4. If no option matches, set choice to null and confidence to 0.0.\n"
                f"5. Never hallucinate or invent an option not in the provided list."
            )
            try:
                result = self.llm_client.generate_json(DropdownMatch, prompt)
                if result.confidence < self.confidence_threshold:
                    result.choice = None
                    result.evidence += " (Rejected: below confidence threshold)"
                return result
            except Exception as e:
                logger.warning("LLM fallback failed: %s", e)
                return DropdownMatch(
                    choice=None,
                    confidence=0.0,
                    evidence=f"LLM fallback error: {str(e)}"
                )

        # No match found above threshold
        return DropdownMatch(
            choice=None,
            confidence=0.0,
            evidence="No matching option found above confidence threshold."
        )
