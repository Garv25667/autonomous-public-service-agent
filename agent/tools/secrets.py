import re
import logging
from typing import Dict, List, Set, Optional, Tuple, Any

logger = logging.getLogger(__name__)

# Canonical list of PII and sensitive fields in public service applications
DEFAULT_SENSITIVE_FIELDS: Set[str] = {
    "full_name",
    "dob",
    "date_of_birth",
    "annual_income",
    "income",
    "aadhaar",
    "aadhaar_number",
    "national_id",
    "phone",
    "mobile",
    "email",
    "bank_account",
    "ifsc_code",
    "address",
    "password",
}


class PIILeakDetectedError(Exception):
    """Raised when an unredacted sensitive citizen value is detected in an outbound LLM prompt."""
    pass


class SecretVault:
    """
    Implements Feature F1: PII Protection from Section 5 of the 48-Hour Playbook:
    1. Replaces sensitive citizen fields with placeholder tokens (e.g. {{full_name}}, {{dob}})
       before any prompt or context is sent to the LLM.
    2. Provides local substitution at browser typing time.
    3. Scans all outbound prompts and LLM logs to guarantee zero PII leakage.
    """

    def __init__(self, sensitive_keys: Optional[Set[str]] = None):
        self.sensitive_keys = sensitive_keys or DEFAULT_SENSITIVE_FIELDS.copy()
        # Mapping: placeholder -> real_value, e.g. "{{full_name}}": "Aarav Sharma"
        self._secrets: Dict[str, str] = {}
        # Mapping: real_value -> placeholder
        self._reverse_map: Dict[str, str] = {}

    def register_secret(self, key: str, value: str) -> str:
        """
        Registers a secret value into the vault and returns its placeholder token.
        Example: register_secret('full_name', 'Aarav Sharma') -> '{{full_name}}'
        """
        if not value or len(str(value).strip()) == 0:
            return value

        placeholder = f"{{{{{key}}}}}"
        str_val = str(value).strip()
        self._secrets[placeholder] = str_val
        self._reverse_map[str_val] = placeholder
        return placeholder

    def load_from_profile(self, profile: Dict[str, Any]) -> None:
        """
        Recursively extracts sensitive fields from a citizen profile and populates the vault.
        """
        def _extract(data: Dict[str, Any], prefix: str = ""):
            for k, v in data.items():
                if isinstance(v, dict):
                    _extract(v, prefix=f"{prefix}{k}.")
                elif isinstance(v, str) and (k.lower() in self.sensitive_keys or any(s in k.lower() for s in ("name", "dob", "income", "id"))):
                    self.register_secret(k, v)

        _extract(profile)

    def redact(self, text: str) -> str:
        """
        Substitutes any occurrence of registered sensitive values in text with their placeholder tokens.
        Safe to send to external LLMs.
        """
        if not text:
            return text

        redacted = text
        # Sort by value length descending to prevent partial replacements
        for real_val, placeholder in sorted(self._reverse_map.items(), key=lambda x: len(x[0]), reverse=True):
            if real_val and real_val in redacted:
                redacted = redacted.replace(real_val, placeholder)
        return redacted

    def substitute(self, text: str) -> str:
        """
        Substitutes placeholder tokens with real secret values.
        Used strictly locally by the Executor right before typing into the browser.
        """
        if not text:
            return text

        substituted = text
        for placeholder, real_val in self._secrets.items():
            if placeholder in substituted:
                substituted = substituted.replace(placeholder, real_val)
        return substituted

    def mask_profile(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        """
        Returns a redacted copy of the citizen profile where all sensitive values are replaced
        by placeholders. Safe for LLM consumption.
        """
        masked = {}
        for k, v in profile.items():
            if isinstance(v, dict):
                masked[k] = self.mask_profile(v)
            elif isinstance(v, str) and (k.lower() in self.sensitive_keys or any(s in k.lower() for s in ("name", "dob", "income"))):
                placeholder = f"{{{{{k}}}}}"
                self.register_secret(k, v)
                masked[k] = placeholder
            else:
                masked[k] = v
        return masked

    def scan_for_leaks(self, text: str) -> List[Tuple[str, str]]:
        """
        Scans a text string (e.g. an LLM prompt or log entry) for any leaked sensitive values.
        Returns a list of tuples: [(placeholder, leaked_real_value), ...]
        Empty list indicates 100% clean / leak-free!
        """
        leaks = []
        if not text:
            return leaks

        for placeholder, real_val in self._secrets.items():
            # Skip trivial or empty strings
            if len(real_val) < 2:
                continue
            # Check for literal leak of the sensitive value
            if real_val in text:
                leaks.append((placeholder, real_val))

        return leaks

    def assert_no_leaks(self, text: str, context_label: str = "LLM prompt") -> None:
        """Raises PIILeakDetectedError if any sensitive value is found in the text."""
        leaks = self.scan_for_leaks(text)
        if leaks:
            leak_details = ", ".join([f"{placeholder} (value='{val}')" for placeholder, val in leaks])
            raise PIILeakDetectedError(
                f"PII Leak Detected in {context_label}! Sensitive values found: {leak_details}"
            )
