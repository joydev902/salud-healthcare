import uuid

from pydantic import BaseModel, Field

from app.models import UserRole


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)


class ProviderRef(BaseModel):
    id: int
    name: str
    group_name: str


class CurrentUserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    providers: list[ProviderRef]
