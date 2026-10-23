import re
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models import UserRole
from app.schemas.auth import ProviderRef

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 12


def _clean_name(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Name is required")
    return value


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime
    providers: list[ProviderRef]


class UserPage(BaseModel):
    items: list[UserOut]
    next_cursor: str | None
    has_more: bool


class UserCreate(BaseModel):
    email: str = Field(max_length=320)
    full_name: str = Field(max_length=200)
    role: UserRole
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=256)
    provider_ids: list[int] = Field(default=[], max_length=1000)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not _EMAIL_RE.match(value):
            raise ValueError("Enter a valid email address")
        return value

    @field_validator("full_name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        return _clean_name(value)


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    role: UserRole | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=MIN_PASSWORD_LENGTH, max_length=256)

    @field_validator("full_name")
    @classmethod
    def valid_name(cls, value: str | None) -> str | None:
        return None if value is None else _clean_name(value)


class ProviderAssignmentUpdate(BaseModel):
    provider_ids: list[int] = Field(max_length=1000)
