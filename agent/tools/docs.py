from pathlib import Path
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

import pypdf
from PIL import Image


class DocumentValidationResult(BaseModel):
    """Validation and inspection results for an uploaded document."""
    valid: bool
    file_path: str
    file_size_bytes: int
    file_size_mb: float
    page_count: int = 1
    extracted_text: str = ""
    is_scanned: bool = False
    mismatches: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None


class DocumentProcessor:
    """
    Implements Feature F4: Document Readiness from Section 5 of the 48-Hour Playbook:
    1. Pre-validates document format and file size against portal rules (< 2 MB) before opening the browser.
    2. Reads and extracts text from PDFs using pypdf.
    3. Cross-checks extracted values against citizen profile to detect mismatches.
    4. Detects scanned (non-extractable) PDFs.
    """

    def __init__(self, max_size_mb: float = 2.0):
        self.max_size_mb = max_size_mb
        self.max_size_bytes = int(max_size_mb * 1024 * 1024)

    def validate_file(
        self,
        file_path: Path,
        expected_profile: Optional[Dict[str, Any]] = None
    ) -> DocumentValidationResult:
        """
        Validates a document (PDF or image) against portal upload rules.
        """
        path = Path(file_path)
        if not path.exists():
            return DocumentValidationResult(
                valid=False,
                file_path=str(path),
                file_size_bytes=0,
                file_size_mb=0.0,
                error_message=f"File not found: {path}"
            )

        file_size = path.stat().st_size
        size_mb = round(file_size / (1024 * 1024), 3)

        # 1. Size constraint check (portal limit 2 MB)
        if file_size > self.max_size_bytes:
            return DocumentValidationResult(
                valid=False,
                file_path=str(path),
                file_size_bytes=file_size,
                file_size_mb=size_mb,
                error_message=f"File size ({size_mb} MB) exceeds portal limit of {self.max_size_mb} MB."
            )

        suffix = path.suffix.lower()
        if suffix not in (".pdf", ".png", ".jpg", ".jpeg"):
            return DocumentValidationResult(
                valid=False,
                file_path=str(path),
                file_size_bytes=file_size,
                file_size_mb=size_mb,
                error_message=f"Unsupported format '{suffix}'. Allowed: .pdf, .jpg, .png"
            )

        # 2. PDF specific processing
        if suffix == ".pdf":
            try:
                reader = pypdf.PdfReader(str(path))
                page_count = len(reader.pages)
                extracted_pages = [page.extract_text() or "" for page in reader.pages]
                full_text = "\n".join(extracted_pages).strip()
                is_scanned = len(full_text) == 0

                # 3. Cross-check against profile if text is extractable
                mismatches = []
                if expected_profile and not is_scanned:
                    personal = expected_profile.get("personal", {})
                    name = personal.get("full_name")
                    if name and not any(part.lower() in full_text.lower() for part in name.split() if len(part) > 2):
                        mismatches.append(f"Student name '{name}' not found in marksheet text.")

                return DocumentValidationResult(
                    valid=len(mismatches) == 0,
                    file_path=str(path),
                    file_size_bytes=file_size,
                    file_size_mb=size_mb,
                    page_count=page_count,
                    extracted_text=full_text,
                    is_scanned=is_scanned,
                    mismatches=mismatches
                )
            except Exception as e:
                return DocumentValidationResult(
                    valid=False,
                    file_path=str(path),
                    file_size_bytes=file_size,
                    file_size_mb=size_mb,
                    error_message=f"Failed to parse PDF document: {str(e)}"
                )

        # 3. Image validation
        try:
            with Image.open(path) as img:
                img.verify()
            return DocumentValidationResult(
                valid=True,
                file_path=str(path),
                file_size_bytes=file_size,
                file_size_mb=size_mb,
                page_count=1
            )
        except Exception as e:
            return DocumentValidationResult(
                valid=False,
                file_path=str(path),
                file_size_bytes=file_size,
                file_size_mb=size_mb,
                error_message=f"Invalid image file: {str(e)}"
            )
