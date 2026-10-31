from typing import Optional, List
from pydantic import BaseModel, Field


class DropdownMatch(BaseModel):
    """Result of mapping a user profile value to available dropdown options."""
    choice: Optional[str] = Field(
        default=None,
        description="The exact text of the matching dropdown option, or null if no valid match exists."
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0."
    )
    evidence: str = Field(
        default="",
        description="Brief reasoning or evidence supporting why this choice was selected."
    )


class PersonalInfo(BaseModel):
    full_name: str
    dob: str
    category: str
    course: str
    state: str
    district: str
    block: str


class EducationInfo(BaseModel):
    college: str
    course_year: str
    marks: str
    annual_income: str
    marksheet_path: str


class CitizenProfile(BaseModel):
    """Pydantic model representing synthetic citizen.json fixture."""
    personal: PersonalInfo
    education: EducationInfo
