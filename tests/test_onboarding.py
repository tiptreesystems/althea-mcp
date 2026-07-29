from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from althea_mcp.config import RuntimeConfig
from althea_mcp.credentials import load_credentials
from althea_mcp.errors import AltheaAPIError
from althea_mcp.models import APIResponse, TokenResponse
from althea_mcp.onboarding import run_setup


class FakeSetupClient:
    def __init__(
        self,
        signin_responses: list[APIResponse | Exception],
        *,
        profile_error: BaseException | None = None,
    ) -> None:
        self.signin_responses = signin_responses
        self.profile_error = profile_error
        self.signin_calls: list[dict[str, Any]] = []
        self.verified: tuple[str, str] | None = None
        self.profile_initialized_with: str | None = None

    async def request_signin_otp(
        self,
        email: str,
        *,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> APIResponse:
        self.signin_calls.append(
            {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
            }
        )
        response = self.signin_responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    async def verify_signin_otp(self, *, token: str, otp: str) -> TokenResponse:
        self.verified = (token, otp)
        return TokenResponse(
            access_token="access-token",
            refresh_token="refresh-token",
            expires_in=300,
            refresh_expires_in=7_776_000,
        )

    async def initialize_profile(self, *, access_token: str) -> APIResponse:
        self.profile_initialized_with = access_token
        if self.profile_error is not None:
            raise self.profile_error
        return APIResponse(status="ok")


def make_config(tmp_path: Path) -> RuntimeConfig:
    return RuntimeConfig(
        app_url="https://althea.example",
        public_site_url="https://www.althea.example",
        thread_key="mcp",
        credentials_path=tmp_path / "credentials.json",
        http_timeout=60,
        poll_interval=2,
        poll_timeout=120,
        user_agent="test",
        log_level="WARNING",
    )


async def test_existing_user_setup_saves_refreshable_session(
    tmp_path: Path,
) -> None:
    client = FakeSetupClient([APIResponse(status="ok", payload={"token": "otp-token"})])
    output: list[str] = []

    result = await run_setup(
        make_config(tmp_path),
        input_fn=lambda _prompt: "Ada@Example.com",
        secret_input_fn=lambda _prompt: "123456",
        output_fn=output.append,
        client=client,
    )

    assert result.configured is True
    assert client.signin_calls == [
        {
            "email": "ada@example.com",
            "first_name": None,
            "last_name": None,
        }
    ]
    assert client.verified == ("otp-token", "123456")
    assert client.profile_initialized_with == "access-token"
    credentials = load_credentials(tmp_path / "credentials.json")
    assert credentials is not None
    assert credentials.access_token == "access-token"
    assert credentials.refresh_token == "refresh-token"
    assert all("refresh-token" not in line for line in output)
    assert any(
        "https://www.althea.example/terms" in line
        and "https://www.althea.example/privacy-policy" in line
        for line in output
    )


async def test_eligible_new_user_is_created_by_same_setup_command(
    tmp_path: Path,
) -> None:
    client = FakeSetupClient(
        [
            APIResponse(
                status="ok",
                payload={
                    "requires_name": True,
                    "email": "ada@example.edu",
                },
            ),
            APIResponse(status="ok", payload={"token": "new-user-token"}),
        ]
    )
    inputs = iter(["ada@example.edu", "Ada", "Lovelace"])

    result = await run_setup(
        make_config(tmp_path),
        input_fn=lambda _prompt: next(inputs),
        secret_input_fn=lambda _prompt: "654321",
        output_fn=lambda _message: None,
        client=client,
    )

    assert result.configured is True
    assert client.signin_calls[1] == {
        "email": "ada@example.edu",
        "first_name": "Ada",
        "last_name": "Lovelace",
    }
    assert client.verified == ("new-user-token", "654321")


async def test_user_without_access_is_sent_to_existing_browser_journey(
    tmp_path: Path,
) -> None:
    client = FakeSetupClient(
        [
            AltheaAPIError(
                "Apply first",
                status_code=403,
                error_code="NO_PROFILE",
            )
        ]
    )
    opened_urls: list[str] = []
    output: list[str] = []

    result = await run_setup(
        make_config(tmp_path),
        input_fn=lambda _prompt: "ada@gmail.com",
        output_fn=output.append,
        open_browser=opened_urls.append,
        client=client,
    )

    assert result.configured is False
    assert result.next_step_url == "https://www.althea.example/apply"
    assert opened_urls == ["https://www.althea.example/apply"]
    assert not (tmp_path / "credentials.json").exists()
    assert any("rerun `althea-mcp setup`" in line for line in output)


async def test_profile_initialization_failure_is_visible_but_does_not_block_credentials(
    tmp_path: Path,
) -> None:
    client = FakeSetupClient(
        [APIResponse(status="ok", payload={"token": "otp-token"})],
        profile_error=AltheaAPIError("temporarily unavailable", status_code=503),
    )
    output: list[str] = []

    result = await run_setup(
        make_config(tmp_path),
        input_fn=lambda _prompt: "ada@example.com",
        secret_input_fn=lambda _prompt: "123456",
        output_fn=output.append,
        client=client,
    )

    assert result.configured is True
    assert any("profile enrichment was not scheduled" in line for line in output)
    credentials = load_credentials(tmp_path / "credentials.json")
    assert credentials is not None
    assert credentials.refresh_token == "refresh-token"


async def test_interrupted_profile_initialization_reports_saved_credentials(
    tmp_path: Path,
) -> None:
    client = FakeSetupClient(
        [APIResponse(status="ok", payload={"token": "otp-token"})],
        profile_error=asyncio.CancelledError(),
    )
    output: list[str] = []

    with pytest.raises(asyncio.CancelledError):
        await run_setup(
            make_config(tmp_path),
            input_fn=lambda _prompt: "ada@example.com",
            secret_input_fn=lambda _prompt: "123456",
            output_fn=output.append,
            client=client,
        )

    credentials = load_credentials(tmp_path / "credentials.json")
    assert credentials is not None
    assert credentials.refresh_token == "refresh-token"
    assert any("Credentials were saved" in line for line in output)
    assert any("Profile initialization was interrupted" in line for line in output)
