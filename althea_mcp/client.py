from __future__ import annotations

from typing import Any, TypeVar
from urllib.parse import quote

import httpx
from pydantic import BaseModel, ValidationError

from althea_mcp.errors import (
    AltheaAPIError,
    AltheaConfigurationError,
    AltheaConnectionError,
    AltheaProtocolError,
)
from althea_mcp.models import (
    ApiKey,
    APIResponse,
    ApiSession,
    Message,
    TokenResponse,
)

ResponseModel = TypeVar("ResponseModel", bound=BaseModel)


class AltheaClient:
    """Async client for the frontend-owned Althea MCP channel."""

    def __init__(
        self,
        *,
        app_url: str,
        api_key: str | None = None,
        timeout: float = 60.0,
        user_agent: str = "althea-mcp",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.app_url = app_url.rstrip("/")
        self.api_key = api_key
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

    async def create_api_key(self, *, access_token: str) -> ApiKey:
        response_payload = await self._request_json(
            "POST",
            "/mcp/api-keys",
            authorization=access_token,
        )
        return self._validate(ApiKey, response_payload, "/mcp/api-keys")

    async def create_dossier(self, *, access_token: str) -> APIResponse:
        """Schedule the same idempotent dossier setup used after web sign-in."""
        response_payload = await self._request_json(
            "POST",
            "/create_dossier",
            authorization=access_token,
        )
        return self._validate(APIResponse, response_payload, "/create_dossier")

    async def list_api_keys(self, *, access_token: str) -> list[ApiSession]:
        response_payload = await self._request_json(
            "GET",
            "/mcp/api-keys",
            authorization=access_token,
        )
        if not isinstance(response_payload, list):
            raise AltheaProtocolError(
                "Althea returned an invalid API-key list: expected a JSON array"
            )
        return [self._validate(ApiSession, item, "/mcp/api-keys") for item in response_payload]

    async def revoke_api_key(
        self,
        api_session_id: str,
        *,
        access_token: str,
    ) -> APIResponse:
        path = f"/mcp/api-keys/{quote(api_session_id, safe='')}"
        response_payload = await self._request_json(
            "DELETE",
            path,
            authorization=access_token,
        )
        return self._validate(APIResponse, response_payload, path)

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
        headers = {"Accept": "application/json"}
        credential = authorization
        if authenticated:
            credential = credential or self._require_api_key()
        if credential:
            headers["Authorization"] = f"Bearer {credential}"

        try:
            response = await self._http_client.request(
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

        if not response.is_success:
            raise self._api_error(response)
        try:
            return response.json()
        except ValueError as exc:
            raise AltheaProtocolError(f"Althea returned invalid JSON for {path}") from exc

    def _require_api_key(self) -> str:
        if self.api_key:
            return self.api_key
        raise AltheaConfigurationError(
            "No Althea API key is configured. Run `althea-mcp setup` first."
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
                "Authentication failed. Run `althea-mcp setup` to create a key "
                "for your main Althea account. Keys from the retired Platform API "
                "do not work with this server."
            )
        return AltheaAPIError(
            message,
            status_code=response.status_code,
            error_code=error_code,
            detail=detail,
        )
