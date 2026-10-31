import os
import json
import time
import logging
from pathlib import Path
from typing import Type, TypeVar, Optional, Any
from pydantic import BaseModel
from dotenv import load_dotenv

from .cache import DiskCache

load_dotenv()

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)


class QuotaExceededError(Exception):
    """Raised when the maximum LLM call budget per run is exceeded."""
    pass


class LLMClient:
    """
    Unified LLM Client adhering to 48-Hour Build Playbook:
    - Target model: Gemini Flash-Lite (configurable via GEMINI_MODEL)
    - Disk cache: keyed on sha256(model + prompt) to ensure zero quota spent on repeated runs
    - Call budget: hard cap on calls per run to prevent quota starvation
    - Schema validation: Pydantic v2 validation on all structured responses
    - Backoff: retry on rate limits / 429 errors
    """

    def __init__(
        self,
        model: Optional[str] = None,
        max_calls_per_run: int = 10,
        cache_dir: Optional[Path] = None,
        api_key: Optional[str] = None,
    ):
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.max_calls = max_calls_per_run
        self.calls_count = 0
        self.cache = DiskCache(cache_dir=cache_dir)
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self._client = None

    def _get_genai_client(self):
        if self._client is None:
            if not self.api_key:
                raise ValueError(
                    "GEMINI_API_KEY is not configured. Set GEMINI_API_KEY in your .env or environment variables."
                )
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def generate_json(
        self,
        schema: Type[T],
        prompt: str,
        system_instruction: Optional[str] = None,
        max_retries: int = 3
    ) -> T:
        """
        Generate structured JSON matching the provided Pydantic schema.
        1. Checks disk cache first (zero quota cost).
        2. Enforces per-run call budget.
        3. Calls Gemini API with structured response schema.
        4. Validates output with Pydantic and writes to disk cache.
        """
        # 1. Check disk cache first
        cached = self.cache.get(self.model, prompt)
        if cached is not None:
            logger.info("Disk cache hit for prompt hash.")
            return schema.model_validate(cached)

        # 2. Check call budget
        if self.calls_count >= self.max_calls:
            raise QuotaExceededError(
                f"LLM call limit reached ({self.calls_count}/{self.max_calls}). Halting to protect free-tier quota."
            )

        client = self._get_genai_client()
        from google.genai import types

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
            temperature=0.0,
            system_instruction=system_instruction
        )

        last_error = None
        for attempt in range(max_retries):
            try:
                self.calls_count += 1
                logger.info(
                    "LLM Call %d/%d to %s",
                    self.calls_count,
                    self.max_calls,
                    self.model
                )

                response = client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config
                )

                raw_text = response.text
                if not raw_text:
                    raise ValueError("Received empty response from Gemini API.")

                # Validate with Pydantic
                parsed = schema.model_validate_json(raw_text)

                # Persist to disk cache
                self.cache.set(self.model, prompt, parsed.model_dump())
                return parsed

            except Exception as e:
                err_str = str(e).lower()
                last_error = e
                # Check for rate limiting / 429
                if "429" in err_str or "resource_exhausted" in err_str:
                    wait_time = (2 ** attempt) * 2
                    logger.warning(
                        "Rate limit encountered (429). Backing off for %ds (attempt %d/%d)...",
                        wait_time,
                        attempt + 1,
                        max_retries
                    )
                    time.sleep(wait_time)
                else:
                    raise e

        raise last_error or RuntimeError("Failed to generate structured JSON.")
