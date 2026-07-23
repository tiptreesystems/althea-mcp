from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from urllib.parse import urlparse

from althea_mcp.credentials import load_credentials

PACKAGE_NAME = "althea-mcp"
DEFAULT_APP_URL = "https://althea.tiptreesystems.com"
DEFAULT_THREAD_KEY = "mcp"
DEFAULT_HTTP_TIMEOUT = 60.0
DEFAULT_POLL_INTERVAL = 2.0
DEFAULT_POLL_TIMEOUT = 120.0
DEFAULT_LOG_LEVEL = "WARNING"
DEFAULT_CREDENTIALS_PATH = Path("~/.config/althea-mcp/credentials.json")
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
THREAD_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _package_version() -> str:
    try:
        return version(PACKAGE_NAME)
    except PackageNotFoundError:
        return "unknown"


PACKAGE_VERSION = _package_version()
DEFAULT_USER_AGENT = f"{PACKAGE_NAME}/{PACKAGE_VERSION}"


@dataclass(frozen=True)
class RuntimeConfig:
    app_url: str
    api_key: str | None
    thread_key: str
    credentials_path: Path
    http_timeout: float
    poll_interval: float
    poll_timeout: float
    user_agent: str
    log_level: str

    def require_api_key(self) -> str:
        if self.api_key:
            return self.api_key
        raise ValueError(
            "Althea MCP is not configured. Run `althea-mcp setup` first, or set ALTHEA_API_KEY."
        )


def normalize_app_url(value: str | None) -> str:
    raw_url = (value or DEFAULT_APP_URL).strip().rstrip("/")
    parsed_url = urlparse(raw_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise ValueError(f"Invalid ALTHEA_APP_URL: expected an http(s) URL, got {value!r}")
    if parsed_url.query or parsed_url.fragment:
        raise ValueError("Invalid ALTHEA_APP_URL: query strings and fragments are not allowed")
    return raw_url


def _parse_positive_float(
    value: str | None,
    *,
    default: float,
    variable_name: str,
) -> float:
    if value is None:
        return default
    try:
        parsed_value = float(value)
    except ValueError:
        raise ValueError(f"Invalid {variable_name}: expected a number of seconds") from None
    if not math.isfinite(parsed_value) or parsed_value <= 0:
        raise ValueError(f"Invalid {variable_name}: expected a finite number greater than 0")
    return parsed_value


def _parse_thread_key(value: str | None) -> str:
    thread_key = (value or DEFAULT_THREAD_KEY).strip()
    if not THREAD_KEY_PATTERN.fullmatch(thread_key):
        raise ValueError(
            "Invalid ALTHEA_THREAD_KEY: use 1-128 letters, digits, dots, "
            "underscores, colons, or hyphens, starting with a letter or digit"
        )
    return thread_key


def _parse_log_level(value: str | None) -> str:
    if value is None:
        return DEFAULT_LOG_LEVEL
    log_level = value.strip().upper()
    if log_level not in LOG_LEVELS:
        raise ValueError(f"Invalid ALTHEA_MCP_LOG_LEVEL: expected one of {', '.join(LOG_LEVELS)}")
    return log_level


def credentials_path_from_env() -> Path:
    configured_path = os.environ.get("ALTHEA_MCP_CREDENTIALS_FILE")
    return Path(configured_path or DEFAULT_CREDENTIALS_PATH).expanduser()


def runtime_config_from_env() -> RuntimeConfig:
    credentials_path = credentials_path_from_env()
    credentials = load_credentials(credentials_path)
    configured_app_url = os.environ.get("ALTHEA_APP_URL")
    app_url = normalize_app_url(
        configured_app_url or (credentials.app_url if credentials is not None else None)
    )
    configured_api_key = os.environ.get("ALTHEA_API_KEY")
    api_key = (
        configured_api_key.strip()
        if configured_api_key
        else credentials.api_key
        if credentials is not None
        else None
    )
    return RuntimeConfig(
        app_url=app_url,
        api_key=api_key,
        thread_key=_parse_thread_key(os.environ.get("ALTHEA_THREAD_KEY")),
        credentials_path=credentials_path,
        http_timeout=_parse_positive_float(
            os.environ.get("ALTHEA_MCP_HTTP_TIMEOUT"),
            default=DEFAULT_HTTP_TIMEOUT,
            variable_name="ALTHEA_MCP_HTTP_TIMEOUT",
        ),
        poll_interval=_parse_positive_float(
            os.environ.get("ALTHEA_MCP_POLL_INTERVAL"),
            default=DEFAULT_POLL_INTERVAL,
            variable_name="ALTHEA_MCP_POLL_INTERVAL",
        ),
        poll_timeout=_parse_positive_float(
            os.environ.get("ALTHEA_MCP_POLL_TIMEOUT"),
            default=DEFAULT_POLL_TIMEOUT,
            variable_name="ALTHEA_MCP_POLL_TIMEOUT",
        ),
        user_agent=os.environ.get("ALTHEA_MCP_USER_AGENT") or DEFAULT_USER_AGENT,
        log_level=_parse_log_level(os.environ.get("ALTHEA_MCP_LOG_LEVEL")),
    )
