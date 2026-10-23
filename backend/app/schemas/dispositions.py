import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models import Disposition
from app.models.enums import USER_SELECTABLE_DISPOSITIONS

MIN_JUSTIFICATION_LENGTH = 10


class DispositionRequest(BaseModel):
    new_disposition: Disposition
    justification: str = Field(max_length=4000)
    expected_version: int = Field(ge=0)

    @field_validator("new_disposition")
    @classmethod
    def _selectable(cls, value: Disposition) -> Disposition:
        if value not in USER_SELECTABLE_DISPOSITIONS:
            raise ValueError("OPEN is not a selectable disposition")
        return value

    @field_validator("justification")
    @classmethod
    def _substantive(cls, value: str) -> str:
        value = value.strip()
        if len(value) < MIN_JUSTIFICATION_LENGTH:
            raise ValueError(
                f"Justification must be at least {MIN_JUSTIFICATION_LENGTH} characters"
            )
        return value


class DispositionResult(BaseModel):
    opportunity_id: uuid.UUID
    current_disposition: Disposition
    disposition_version: int
    changed_at: datetime


class DispositionHistoryItem(BaseModel):
    id: int
    changed_at: datetime
    changed_by_email: str
    changed_by_name: str
    old_status: Disposition
    new_status: Disposition
    note: str
    old_version: int
    new_version: int
