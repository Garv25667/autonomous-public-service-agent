import hashlib
import json
from pathlib import Path
from typing import Optional, Dict, Any


class DiskCache:
    """
    Disk-based cache for LLM responses keyed by sha256(model + prompt).
    Saves API quota and makes automated test runs deterministic and cost-free.
    """

    def __init__(self, cache_dir: Optional[Path] = None):
        if cache_dir is None:
            # Default to <repo_root>/.cache/llm
            self.cache_dir = Path(__file__).resolve().parents[2] / ".cache" / "llm"
        else:
            self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _hash_key(self, model: str, prompt: str) -> str:
        content = f"{model}:::{prompt}".encode("utf-8")
        return hashlib.sha256(content).hexdigest()

    def get(self, model: str, prompt: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached structured output if present, or None."""
        key = self._hash_key(model, prompt)
        cache_file = self.cache_dir / f"{key}.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return None
        return None

    def set(self, model: str, prompt: str, data: Dict[str, Any]) -> None:
        """Store structured output on disk."""
        key = self._hash_key(model, prompt)
        cache_file = self.cache_dir / f"{key}.json"
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
