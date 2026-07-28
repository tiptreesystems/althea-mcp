from __future__ import annotations

import re
import time
import webbrowser
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from althea_mcp.client import AltheaClient
from althea_mcp.config import RuntimeConfig
from althea_mcp.credentials import save_credentials
from althea_mcp.errors import AltheaAPIError, AltheaError, AltheaProtocolError
from althea_mcp.models import APIResponse, StoredCredentials

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
ACCESS_ERROR_CODES = frozenset({"NO_PROFILE", "PROFILE_NOT_ACTIVATED"})


@dataclass(frozen=True)
class SetupResult:
    configured: bool
    credentials_path: Path | None = None
    next_step_url: str | None = None


async def run_setup(
    config: RuntimeConfig,
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
    open_browser: Callable[[str], object] = webbrowser.open,
    client: AltheaClient | None = None,
    browser_enabled: bool = True,
) -> SetupResult:
    """Configure the local MCP server through Althea's unified OTP flow."""
    output_fn("Connect your personal Althea")
    output_fn("-----------------------------")
    output_fn(
        f"By continuing, you agree to {config.app_url}/terms and {config.app_url}/privacy-policy."
    )
    email = _prompt_email(input_fn, output_fn)
    althea_client = client or AltheaClient(
        app_url=config.app_url,
        timeout=config.http_timeout,
        user_agent=config.user_agent,
    )
    owns_client = client is None

    try:
        signin_response = await _request_signin(
            althea_client,
            email,
            input_fn=input_fn,
            output_fn=output_fn,
        )
        token = _signin_token(signin_response)
        output_fn(f"A verification code was sent to {email}.")
        otp = _prompt_required(input_fn, output_fn, "Verification code: ")
        token_response = await althea_client.verify_signin_otp(
            token=token,
            otp=otp,
        )
        if not token_response.refresh_token:
            raise AltheaProtocolError("Althea did not issue a refresh token. Please rerun setup.")
        issued_at = time.time()
        credentials = StoredCredentials(
            app_url=config.app_url,
            access_token=token_response.access_token,
            refresh_token=token_response.refresh_token,
            access_token_expires_at=issued_at + token_response.expires_in,
            refresh_token_expires_at=(
                issued_at + token_response.refresh_expires_in
                if token_response.refresh_expires_in is not None
                else None
            ),
        )
        save_credentials(config.credentials_path, credentials)
        await _schedule_dossier(
            althea_client,
            access_token=token_response.access_token,
            output_fn=output_fn,
        )
    except AltheaAPIError as exc:
        if exc.status_code == 403 and exc.error_code in ACCESS_ERROR_CODES:
            return _open_access_request(
                config.app_url,
                output_fn=output_fn,
                open_browser=open_browser,
                browser_enabled=browser_enabled,
            )
        raise
    finally:
        if owns_client:
            await althea_client.close()

    output_fn("")
    output_fn("Althea MCP is ready.")
    output_fn(f"Credentials saved securely to {config.credentials_path}")
    output_fn("Add the MCP server to your client, then ask it to call `ask_althea`.")
    return SetupResult(
        configured=True,
        credentials_path=config.credentials_path,
    )


async def _schedule_dossier(
    client: AltheaClient,
    *,
    access_token: str,
    output_fn: Callable[[str], None],
) -> None:
    try:
        await client.create_dossier(access_token=access_token)
    except AltheaError as exc:
        # Dossier generation enriches the agent but is not required for the
        # credential handoff. The frontend retries it on a later web sign-in.
        output_fn(f"Note: Althea profile enrichment was not scheduled: {exc}")


async def _request_signin(
    client: AltheaClient,
    email: str,
    *,
    input_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
) -> APIResponse:
    output_fn("Checking your Althea account...")
    response = await client.request_signin_otp(email)
    payload = response.payload or {}
    if not payload.get("requires_name"):
        return response

    output_fn("This email is eligible for a new Althea account.")
    first_name = _prompt_required(input_fn, output_fn, "First name: ")
    last_name = _prompt_required(input_fn, output_fn, "Last name: ")
    return await client.request_signin_otp(
        email,
        first_name=first_name,
        last_name=last_name,
    )


def _signin_token(response: APIResponse) -> str:
    payload = response.payload or {}
    token = payload.get("token")
    if not isinstance(token, str) or not token:
        raise AltheaProtocolError("Althea did not issue a verification token. Please rerun setup.")
    return token


def _prompt_email(
    input_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
) -> str:
    while True:
        email = input_fn("Email: ").strip().lower()
        if EMAIL_PATTERN.fullmatch(email):
            return email
        output_fn("Enter a valid email address.")


def _prompt_required(
    input_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
    prompt: str,
) -> str:
    while True:
        value = input_fn(prompt).strip()
        if value:
            return value
        output_fn("This field is required.")


def _open_access_request(
    app_url: str,
    *,
    output_fn: Callable[[str], None],
    open_browser: Callable[[str], object],
    browser_enabled: bool,
) -> SetupResult:
    access_url = f"{app_url}/apply"
    output_fn("")
    output_fn("This email does not have an active Althea account yet.")
    output_fn(f"Request access at: {access_url}")
    if browser_enabled:
        with suppress(Exception):
            open_browser(access_url)
    output_fn("After your account is active, rerun `althea-mcp setup`.")
    return SetupResult(configured=False, next_step_url=access_url)
