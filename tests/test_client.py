from __future__ import annotations

import time
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from althea_mcp.client import AltheaClient
from althea_mcp.credentials import load_credentials, save_credentials
from althea_mcp.errors import (
    AltheaAPIError,
    AltheaConfigurationError,
    AltheaProtocolError,
)
from althea_mcp.models import StoredCredentials


def message_payload(
    *,
    message_id: str,
    sender: str,
    content: str,
    created_at: float,
) -> dict[str, Any]:
    return {
        "id": message_id,
        "agent_session_id": "session-1",
        "payload": {
            "content": content,
            "sender": sender,
            "attachments": [],
        },
        "read": False,
        "created_at": created_at,
    }


def mock_client(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    credentials_path: Path | None = None,
) -> tuple[AltheaClient, httpx.AsyncClient]:
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return (
        AltheaClient(
            app_url="https://althea.example",
            credentials_path=credentials_path,
            http_client=http_client,
        ),
        http_client,
    )


async def test_auth_and_message_journey_uses_frontend_routes(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    credentials_path = tmp_path / "credentials.json"
    save_credentials(
        credentials_path,
        StoredCredentials(
            app_url="https://althea.example",
            access_token="managed-access-token",
            refresh_token="managed-refresh-token",
            access_token_expires_at=time.time() + 3600 * 24,
            refresh_token_expires_at=time.time() + 3600 * 24 * 30,
        ),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/otp/signin":
            assert "authorization" not in request.headers
            return httpx.Response(
                200,
                json={
                    "status": "ok",
                    "payload": {"token": "otp-token"},
                },
            )
        if request.url.path == "/mcp/auth/otp/signin/verify":
            return httpx.Response(
                200,
                json={
                    "access_token": "access-token",
                    "refresh_token": "refresh-token",
                    "expires_in": 300,
                    "refresh_expires_in": 3600,
                },
            )
        if request.url.path == "/initialize_profile":
            assert request.headers["Authorization"] == "Bearer access-token"
            return httpx.Response(
                200,
                json={
                    "status": "ok",
                    "message": "Profile initialization scheduled.",
                },
            )
        if request.method == "POST":
            assert request.headers["Authorization"] == "Bearer managed-access-token"
            return httpx.Response(
                200,
                json=message_payload(
                    message_id="user-message",
                    sender="user",
                    content="hello",
                    created_at=10,
                ),
            )
        assert request.headers["Authorization"] == "Bearer managed-access-token"
        assert request.url.params["sender"] == "assistant"
        assert request.url.params["created_after"] == "10.0"
        return httpx.Response(
            200,
            json=[
                message_payload(
                    message_id="assistant-message",
                    sender="assistant",
                    content="hi",
                    created_at=11,
                )
            ],
        )

    client, http_client = mock_client(handler, credentials_path=credentials_path)
    try:
        signin = await client.request_signin_otp("ada@example.com")
        token = await client.verify_signin_otp(
            token=signin.payload["token"],
            otp="123456",
        )
        profile = await client.initialize_profile(access_token=token.access_token)
        sent = await client.send_message(thread_key="codex:main", content="hello")
        messages = await client.get_messages(
            thread_key="codex:main",
            sender="assistant",
            created_after=sent.created_at,
        )
    finally:
        await http_client.aclose()

    assert profile.status == "ok"
    assert token.refresh_token == "refresh-token"
    assert messages[0].payload.content == "hi"
    message_requests = [request for request in requests if "/mcp/threads/" in request.url.path]
    assert all(
        request.url.path == "/mcp/threads/codex:main/messages" for request in message_requests
    )


async def test_access_error_preserves_server_code() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={
                "detail": {
                    "error_code": "NO_PROFILE",
                    "message": "You must apply for access.",
                }
            },
        )

    client, http_client = mock_client(handler)
    try:
        with pytest.raises(AltheaAPIError) as error:
            await client.request_signin_otp("ada@example.com")
    finally:
        await http_client.aclose()

    assert error.value.status_code == 403
    assert error.value.error_code == "NO_PROFILE"
    assert str(error.value) == "Althea request failed (HTTP 403)"
    assert error.value.detail == {"error_code": "NO_PROFILE"}


async def test_profile_initialization_falls_back_for_older_frontend() -> None:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        if request.url.path == "/initialize_profile":
            return httpx.Response(404, json={"detail": "Not Found"})
        return httpx.Response(200, json={"status": "ok"})

    client, http_client = mock_client(handler)
    try:
        response = await client.initialize_profile(access_token="access-token")
    finally:
        await http_client.aclose()

    assert response.status == "ok"
    assert requested_paths == ["/initialize_profile", "/create_dossier"]


async def test_invalid_token_response_does_not_echo_payload() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"access_token": "sensitive-access-token"},
        )

    client, http_client = mock_client(handler)
    try:
        with pytest.raises(AltheaProtocolError) as error:
            await client.verify_signin_otp(token="otp-token", otp="123456")
    finally:
        await http_client.aclose()

    assert "sensitive-access-token" not in str(error.value)
    formatted_traceback = "".join(traceback.format_exception(error.value))
    assert "sensitive-access-token" not in formatted_traceback
    assert error.value.__cause__ is None


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(
            422,
            json={
                "detail": [
                    {
                        "msg": "Invalid input",
                        "input": {
                            "refresh_token": "sensitive-refresh-token",
                            "otp": "sensitive-otp",
                        },
                    }
                ]
            },
        ),
        httpx.Response(
            500,
            text="sensitive-refresh-token and sensitive-otp",
        ),
        httpx.Response(
            400,
            json={
                "detail": {
                    "message": "sensitive-refresh-token and sensitive-otp",
                }
            },
        ),
    ],
)
def test_sensitive_api_errors_do_not_echo_raw_bodies(
    response: httpx.Response,
) -> None:
    error = AltheaClient._api_error(response, path="/mcp/auth/token")

    rendered_error = f"{error!s} {error.detail!r}"
    assert "sensitive-refresh-token" not in rendered_error
    assert "sensitive-otp" not in rendered_error
    assert str(error) == f"Althea request failed (HTTP {response.status_code})"


async def test_rejected_access_token_is_refreshed_and_retried(tmp_path: Path) -> None:
    credentials_path = tmp_path / "credentials.json"
    save_credentials(
        credentials_path,
        StoredCredentials(
            app_url="https://althea.example",
            access_token="rejected-access-token",
            refresh_token="old-refresh-token",
            access_token_expires_at=time.time() + 3600 * 24,
            refresh_token_expires_at=time.time() + 3600 * 24 * 30,
        ),
    )
    message_attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal message_attempts
        if request.url.path == "/mcp/auth/token":
            assert request.read().decode() == '{"refresh_token":"old-refresh-token"}'
            return httpx.Response(
                200,
                json={
                    "access_token": "new-access-token",
                    "refresh_token": "new-refresh-token",
                    "expires_in": 3600 * 24,
                    "refresh_expires_in": 3600 * 24 * 29,
                },
            )

        message_attempts += 1
        if message_attempts == 1:
            assert request.headers["Authorization"] == "Bearer rejected-access-token"
            return httpx.Response(401, json={"detail": "Unauthorized"})
        assert request.headers["Authorization"] == "Bearer new-access-token"
        return httpx.Response(200, json=[])

    client, http_client = mock_client(handler, credentials_path=credentials_path)
    try:
        assert await client.get_messages(thread_key="mcp") == []
    finally:
        await http_client.aclose()

    credentials = load_credentials(credentials_path)
    assert credentials is not None
    assert credentials.access_token == "new-access-token"
    assert credentials.refresh_token == "new-refresh-token"
    assert message_attempts == 2


async def test_credentials_are_not_sent_to_another_server(tmp_path: Path) -> None:
    credentials_path = tmp_path / "credentials.json"
    save_credentials(
        credentials_path,
        StoredCredentials(
            app_url="https://other.example",
            access_token="access-token",
            refresh_token="refresh-token",
            access_token_expires_at=time.time() + 3600 * 24,
            refresh_token_expires_at=time.time() + 3600 * 24 * 30,
        ),
    )

    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("The credential must be rejected before any request")

    client, http_client = mock_client(handler, credentials_path=credentials_path)
    try:
        with pytest.raises(AltheaConfigurationError, match="bound to"):
            await client.get_messages(thread_key="mcp")
    finally:
        await http_client.aclose()
