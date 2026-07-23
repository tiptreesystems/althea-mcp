from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class APIResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: Literal["ok", "error", "fail"]
    message: str | None = None
    payload: dict[str, Any] | None = None
    status_code: int | None = None


class TokenResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    access_token: str
    token_type: str = "Bearer"  # noqa: S105 - OAuth token type, not a credential
    expires_in: float
    refresh_token: str | None = None
    scope: str | None = None


class ApiKey(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    api_key: str
    created_at: float
    expires_at: float
    revoked_at: float | None = None


class ApiSession(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    created_at: float
    expires_at: float
    revoked_at: float | None = None
    info: dict[str, Any] | None = None


class MessagePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    content: str | None = None
    sender: Literal["user", "assistant", "system"] | str | None = None
    channel_type: str | None = None
    attachments: list[dict[str, Any]] = Field(default_factory=list)


class Message(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    agent_session_id: str
    payload: MessagePayload
    read: bool
    created_at: float
    info: dict[str, Any] | None = None


class StoredCredentials(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    app_url: str
    api_key: str = Field(min_length=1)
