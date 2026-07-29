from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlparse

from althea_mcp.credentials import load_credentials
from althea_mcp.errors import AltheaConfigurationError
from althea_mcp.models import StoredCredentials

PACKAGE_NAME = "althea-mcp"
DEFAULT_APP_URL = "https://althea.tiptreesystems.com"
DEFAULT_PUBLIC_SITE_URL = "https://tiptreesystems.com"
PUBLIC_SITE_URL_BY_APP_URL = {
    "https://althea.dev.tiptreesystems.com": "https://dev.tiptreesystems.com",
}
DEFAULT_THREAD_KEY = "mcp"
DEFAULT_HTTP_TIMEOUT = 60.0
DEFAULT_POLL_INTERVAL = 2.0
DEFAULT_POLL_TIMEOUT = 120.0
DEFAULT_LOG_LEVEL = "WARNING"
DEFAULT_CREDENTIALS_PATH = Path("~/.config/althea-mcp/credentials.json")
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
THREAD_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
HOST_LABEL_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


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
    public_site_url: str
    thread_key: str
    credentials_path: Path
    http_timeout: float
    poll_interval: float
    poll_timeout: float
    user_agent: str
    log_level: str

    def require_credentials(self) -> StoredCredentials:
        credentials = load_credentials(self.credentials_path)
        if credentials is None:
            raise ValueError("Althea MCP is not configured. Run `althea-mcp setup` first.")
        return credentials


def _is_loopback_hostname(hostname: str | None) -> bool:
    if hostname is None:
        return False
    if hostname == "localhost" or hostname.endswith(".localhost"):
        return True
    try:
        return ip_address(hostname).is_loopback
    except ValueError:
        return False


def _is_valid_hostname(hostname: str | None) -> bool:
    if hostname is None:
        return False
    try:
        ip_address(hostname)
        return True
    except ValueError:
        pass

    normalized_hostname = hostname.rstrip(".")
    if not normalized_hostname or len(normalized_hostname) > 253:
        return False
    try:
        ascii_hostname = normalized_hostname.encode("idna").decode("ascii")
    except UnicodeError:
        return False
    return all(
        HOST_LABEL_PATTERN.fullmatch(label) is not None for label in ascii_hostname.split(".")
    )


def _normalize_base_url(
    value: str | None,
    *,
    default: str,
    variable_name: str,
) -> str:
    raw_url = (value or default).strip().rstrip("/")
    try:
        parsed_url = urlparse(raw_url)
    except ValueError:
        raise ValueError(f"Invalid {variable_name}: expected an http(s) origin") from None
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise ValueError(f"Invalid {variable_name}: expected an http(s) origin")
    if not _is_valid_hostname(parsed_url.hostname):
        raise ValueError(f"Invalid {variable_name}: expected a valid hostname")
    try:
        port = parsed_url.port
    except ValueError:
        raise ValueError(f"Invalid {variable_name}: expected a valid port") from None
    if port == 0:
        raise ValueError(f"Invalid {variable_name}: expected a valid port")
    if parsed_url.username is not None or parsed_url.password is not None:
        raise ValueError(f"Invalid {variable_name}: embedded credentials are not allowed")
    if parsed_url.path not in {"", "/"} or parsed_url.params:
        raise ValueError(f"Invalid {variable_name}: paths are not allowed")
    if parsed_url.query or parsed_url.fragment:
        raise ValueError(f"Invalid {variable_name}: query strings and fragments are not allowed")
    if parsed_url.scheme == "http" and not _is_loopback_hostname(parsed_url.hostname):
        raise ValueError(f"Invalid {variable_name}: HTTPS is required except for localhost")
    return raw_url


def normalize_app_url(value: str | None) -> str:
    return _normalize_base_url(
        value,
        default=DEFAULT_APP_URL,
        variable_name="ALTHEA_APP_URL",
    )


def normalize_public_site_url(value: str | None) -> str:
    return _normalize_base_url(
        value,
        default=DEFAULT_PUBLIC_SITE_URL,
        variable_name="ALTHEA_PUBLIC_SITE_URL",
    )


def public_site_url_from_env(app_url: str) -> str:
    return normalize_public_site_url(
        os.environ.get("ALTHEA_PUBLIC_SITE_URL") or PUBLIC_SITE_URL_BY_APP_URL.get(app_url)
    )


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


def runtime_config_from_env(
    *,
    validate_saved_credentials: bool = True,
) -> RuntimeConfig:
    credentials_path = credentials_path_from_env()
    try:
        credentials = load_credentials(credentials_path)
    except AltheaConfigurationError:
        if validate_saved_credentials:
            raise
        credentials = None
    configured_app_url = os.environ.get("ALTHEA_APP_URL")
    app_url = normalize_app_url(
        configured_app_url or (credentials.app_url if credentials is not None else None)
    )
    public_site_url = public_site_url_from_env(app_url)
    if (
        validate_saved_credentials
        and credentials is not None
        and normalize_app_url(credentials.app_url) != app_url
    ):
        raise AltheaConfigurationError(
            f"Saved Althea MCP credentials are bound to {credentials.app_url}, "
            f"not {app_url}. Run `althea-mcp setup --app-url {app_url}` to sign "
            "in to the configured server."
        )
    if validate_saved_credentials and credentials is None and os.environ.get("ALTHEA_API_KEY"):
        raise ValueError(
            "ALTHEA_API_KEY is no longer supported. Run `althea-mcp setup` "
            "to create a refreshable MCP session."
        )
    return RuntimeConfig(
        app_url=app_url,
        public_site_url=public_site_url,
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
