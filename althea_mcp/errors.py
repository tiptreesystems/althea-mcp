from __future__ import annotations

from typing import Any


class AltheaError(RuntimeError):
    """Base class for user-facing Althea MCP errors."""


class AltheaConfigurationError(AltheaError):
    """Raised when local Althea MCP configuration is missing or invalid."""


class AltheaConnectionError(AltheaError):
    """Raised when the Althea frontend cannot be reached."""


class AltheaProtocolError(AltheaError):
    """Raised when the frontend returns an unexpected response shape."""


class AltheaAPIError(AltheaError):
    """A structured non-success response from the Althea frontend."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        error_code: str | None = None,
        detail: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.detail = detail
