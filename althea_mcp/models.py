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
    refresh_expires_in: float | None = None
    scope: str | None = None


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

    version: Literal[2] = 2
    app_url: str
    access_token: str = Field(min_length=1)
    refresh_token: str = Field(min_length=1)
    access_token_expires_at: float
    refresh_token_expires_at: float | None = None
