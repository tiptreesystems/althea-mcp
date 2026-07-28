from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any, TypeVar
from urllib.parse import quote

import httpx
from filelock import Timeout
from pydantic import BaseModel, ValidationError

from althea_mcp.credentials import (
    credentials_lock,
    load_credentials,
    save_credentials,
)
from althea_mcp.errors import (
    AltheaAPIError,
    AltheaAuthenticationError,
    AltheaConfigurationError,
    AltheaConnectionError,
    AltheaProtocolError,
)
from althea_mcp.models import (
    APIResponse,
    Message,
    StoredCredentials,
    TokenResponse,
)

ResponseModel = TypeVar("ResponseModel", bound=BaseModel)
ACCESS_TOKEN_REFRESH_MARGIN_SECONDS = 60 * 90


class AltheaClient:
    """Async client for the frontend-owned Althea MCP channel."""

    def __init__(
        self,
        *,
        app_url: str,
        credentials_path: Path | None = None,
        timeout: float = 60.0,
        user_agent: str = "althea-mcp",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.app_url = app_url.rstrip("/")
        self.credentials_path = credentials_path
        self._refresh_lock = asyncio.Lock()
        self._owns_http_client = http_client is None
        self._http_client = http_client or httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": user_agent},
        )

    async def __aenter__(self) -> AltheaClient:
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self.close()

    async def close(self) -> None:
        if self._owns_http_client:
            await self._http_client.aclose()

    async def request_signin_otp(
        self,
        email: str,
        *,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> APIResponse:
        payload: dict[str, str] = {"email": email}
        if first_name is not None:
            payload["first_name"] = first_name
        if last_name is not None:
            payload["last_name"] = last_name
        response_payload = await self._request_json(
            "POST",
            "/otp/signin",
            json=payload,
        )
        return self._validate(APIResponse, response_payload, "/otp/signin")

    async def verify_signin_otp(self, *, token: str, otp: str) -> TokenResponse:
        response_payload = await self._request_json(
            "POST",
            "/mcp/auth/otp/signin/verify",
            json={"token": token, "otp": otp},
        )
        return self._validate(
            TokenResponse,
            response_payload,
            "/mcp/auth/otp/signin/verify",
        )

    async def create_dossier(self, *, access_token: str) -> APIResponse:
        """Schedule the same idempotent dossier setup used after web sign-in."""
        response_payload = await self._request_json(
            "POST",
            "/create_dossier",
            authorization=access_token,
        )
        return self._validate(APIResponse, response_payload, "/create_dossier")

    async def send_message(self, *, thread_key: str, content: str) -> Message:
        path = f"/mcp/threads/{quote(thread_key, safe='')}/messages"
        response_payload = await self._request_json(
            "POST",
            path,
            json={"content": content},
            authenticated=True,
        )
        return self._validate(Message, response_payload, path)

    async def get_messages(
        self,
        *,
        thread_key: str,
        sender: str | None = None,
        created_after: float | None = None,
        created_before: float | None = None,
        offset: int = 0,
        limit: int = 10,
        most_recent_first: bool = False,
    ) -> list[Message]:
        path = f"/mcp/threads/{quote(thread_key, safe='')}/messages"
        parameters: dict[str, str | int | float | bool] = {
            "offset": offset,
            "limit": limit,
            "most_recent_first": most_recent_first,
        }
        if sender is not None:
            parameters["sender"] = sender
        if created_after is not None:
            parameters["created_after"] = created_after
        if created_before is not None:
            parameters["created_before"] = created_before
        response_payload = await self._request_json(
            "GET",
            path,
            params=parameters,
            authenticated=True,
        )
        if not isinstance(response_payload, list):
            raise AltheaProtocolError(
                "Althea returned an invalid message list: expected a JSON array"
            )
        return [self._validate(Message, item, path) for item in response_payload]

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str | int | float | bool] | None = None,
        json: dict[str, Any] | None = None,
        authorization: str | None = None,
        authenticated: bool = False,
    ) -> Any:
        credential = authorization
        managed_authentication = authenticated and authorization is None
        if managed_authentication:
            credential = await self._managed_access_token()

        response = await self._perform_request(
            method,
            path,
            params=params,
            json=json,
            credential=credential,
        )
        if response.status_code == 401 and managed_authentication:
            credential = await self._refresh_access_token(
                force=True,
                rejected_access_token=credential,
            )
            response = await self._perform_request(
                method,
                path,
                params=params,
                json=json,
                credential=credential,
            )
            if response.status_code == 401:
                raise self._reauthentication_error()

        if not response.is_success:
            raise self._api_error(response)
        try:
            return response.json()
        except ValueError as exc:
            raise AltheaProtocolError(f"Althea returned invalid JSON for {path}") from exc

    async def _perform_request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str | int | float | bool] | None,
        json: dict[str, Any] | None,
        credential: str | None,
    ) -> httpx.Response:
        headers = {"Accept": "application/json"}
        if credential:
            headers["Authorization"] = f"Bearer {credential}"
        try:
            return await self._http_client.request(
                method,
                f"{self.app_url}{path}",
                params=params,
                json=json,
                headers=headers,
            )
        except httpx.TimeoutException as exc:
            raise AltheaConnectionError(
                f"Althea did not respond in time at {self.app_url}"
            ) from exc
        except httpx.RequestError as exc:
            raise AltheaConnectionError(f"Could not reach Althea at {self.app_url}: {exc}") from exc

    async def _managed_access_token(self) -> str:
        credentials = self._load_managed_credentials()
        current_time = time.time()
        if credentials.access_token_expires_at > current_time + ACCESS_TOKEN_REFRESH_MARGIN_SECONDS:
            return credentials.access_token
        if (
            credentials.refresh_token_expires_at is not None
            and credentials.refresh_token_expires_at
            <= current_time + ACCESS_TOKEN_REFRESH_MARGIN_SECONDS
        ):
            raise self._reauthentication_error()
        return await self._refresh_access_token(force=False)

    async def _refresh_access_token(
        self,
        *,
        force: bool,
        rejected_access_token: str | None = None,
    ) -> str:
        async with self._refresh_lock:
            credentials_path = self._require_credentials_path()
            lock = credentials_lock(credentials_path)
            try:
                lock_handle = await asyncio.to_thread(lock.acquire)
            except Timeout as exc:
                raise AltheaConfigurationError(
                    "Timed out waiting for another Althea MCP process to "
                    "finish refreshing the shared session."
                ) from exc

            try:
                credentials = self._load_managed_credentials()
                current_time = time.time()
                access_token_is_fresh = (
                    credentials.access_token_expires_at
                    > current_time + ACCESS_TOKEN_REFRESH_MARGIN_SECONDS
                )
                another_process_refreshed = (
                    rejected_access_token is not None
                    and credentials.access_token != rejected_access_token
                )
                if access_token_is_fresh and (not force or another_process_refreshed):
                    return credentials.access_token
                if (
                    credentials.refresh_token_expires_at is not None
                    and credentials.refresh_token_expires_at
                    <= current_time + ACCESS_TOKEN_REFRESH_MARGIN_SECONDS
                ):
                    raise self._reauthentication_error()

                try:
                    response_payload = await self._request_json(
                        "POST",
                        "/mcp/auth/token",
                        json={"refresh_token": credentials.refresh_token},
                    )
                except AltheaAPIError as exc:
                    if exc.status_code in {400, 401, 403}:
                        raise self._reauthentication_error() from exc
                    raise

                token_response = self._validate(
                    TokenResponse,
                    response_payload,
                    "/mcp/auth/token",
                )
                if not token_response.refresh_token:
                    raise AltheaProtocolError(
                        "Althea refreshed the access token without rotating the refresh token."
                    )

                issued_at = time.time()
                refreshed_credentials = StoredCredentials(
                    app_url=self.app_url,
                    access_token=token_response.access_token,
                    refresh_token=token_response.refresh_token,
                    access_token_expires_at=issued_at + token_response.expires_in,
                    refresh_token_expires_at=(
                        issued_at + token_response.refresh_expires_in
                        if token_response.refresh_expires_in is not None
                        else credentials.refresh_token_expires_at
                    ),
                )
                save_credentials(
                    credentials_path,
                    refreshed_credentials,
                    acquire_lock=False,
                )
                if (
                    refreshed_credentials.access_token_expires_at
                    <= issued_at + ACCESS_TOKEN_REFRESH_MARGIN_SECONDS
                ):
                    raise self._reauthentication_error()
                return refreshed_credentials.access_token
            finally:
                lock.release()
                del lock_handle

    def _load_managed_credentials(self) -> StoredCredentials:
        credentials_path = self._require_credentials_path()
        credentials = load_credentials(credentials_path)
        if credentials is None:
            raise AltheaConfigurationError(
                "Althea MCP is not configured. Run `althea-mcp setup` first."
            )
        return credentials

    def _require_credentials_path(self) -> Path:
        if self.credentials_path is None:
            raise AltheaConfigurationError(
                "No Althea MCP credential store is configured. Run `althea-mcp setup` first."
            )
        return self.credentials_path

    @staticmethod
    def _reauthentication_error() -> AltheaAuthenticationError:
        return AltheaAuthenticationError(
            "Your Althea MCP sign-in has expired or was revoked. Run "
            "`althea-mcp setup` in a separate terminal, then retry this call."
        )

    @staticmethod
    def _validate(
        model: type[ResponseModel],
        payload: Any,
        path: str,
    ) -> ResponseModel:
        try:
            return model.model_validate(payload)
        except ValidationError as exc:
            raise AltheaProtocolError(
                f"Althea returned an unexpected response for {path}: {exc}"
            ) from exc

    @staticmethod
    def _api_error(response: httpx.Response) -> AltheaAPIError:
        try:
            response_payload: Any = response.json()
        except ValueError:
            response_payload = response.text.strip()

        detail = (
            response_payload.get("detail")
            if isinstance(response_payload, dict)
            else response_payload
        )
        error_code = detail.get("error_code") if isinstance(detail, dict) else None
        if isinstance(detail, dict):
            message = detail.get("message") or str(detail)
        elif detail:
            message = str(detail)
        else:
            message = response.reason_phrase or "Althea request failed"

        if response.status_code == 401:
            message = (
                "Authentication failed. Run `althea-mcp setup` in a separate terminal, then retry."
            )
        return AltheaAPIError(
            message,
            status_code=response.status_code,
            error_code=error_code,
            detail=detail,
        )
