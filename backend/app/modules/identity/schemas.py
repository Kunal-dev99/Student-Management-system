"""Pydantic request/response contracts for identity (arch §11.1 — camelCase over the wire)."""
from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field
from pydantic.alias_generators import to_camel


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class LoginRequest(_CamelModel):
    email: EmailStr
    password: str


class TokenPair(_CamelModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(_CamelModel):
    refresh_token: str


class PasswordResetRequest(_CamelModel):
    email: EmailStr


class PasswordResetConfirm(_CamelModel):
    token: str
    new_password: str


class MeResponse(_CamelModel):
    authenticated: bool
    user_id: uuid.UUID | None = None
    email: str | None = None
    person_id: uuid.UUID | None = None
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
