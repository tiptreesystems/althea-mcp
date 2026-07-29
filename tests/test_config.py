from __future__ import annotations

from pathlib import Path

import pytest

from althea_mcp.config import runtime_config_from_env
from althea_mcp.credentials import save_credentials
from althea_mcp.errors import AltheaConfigurationError
from althea_mcp.models import StoredCredentials

CONFIG_ENVIRONMENT_VARIABLES = (
    "ALTHEA_API_KEY",
    "ALTHEA_APP_URL",
    "ALTHEA_PUBLIC_SITE_URL",
    "ALTHEA_THREAD_KEY",
    "ALTHEA_MCP_CREDENTIALS_FILE",
    "ALTHEA_MCP_HTTP_TIMEOUT",
    "ALTHEA_MCP_POLL_INTERVAL",
    "ALTHEA_MCP_POLL_TIMEOUT",
    "ALTHEA_MCP_USER_AGENT",
    "ALTHEA_MCP_LOG_LEVEL",
)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    for variable_name in CONFIG_ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(variable_name, raising=False)
    credentials_path = tmp_path / "credentials.json"
    monkeypatch.setenv("ALTHEA_MCP_CREDENTIALS_FILE", str(credentials_path))
    return credentials_path


def test_config_loads_saved_credentials(clean_environment: Path) -> None:
    save_credentials(
        clean_environment,
        StoredCredentials(
            app_url="https://althea.example/",
            access_token="access-token",
            refresh_token="refresh-token",
            access_token_expires_at=10_000,
            refresh_token_expires_at=20_000,
        ),
    )

    config = runtime_config_from_env()

    assert config.app_url == "https://althea.example"
    assert config.public_site_url == "https://tiptreesystems.com"
    assert config.require_credentials().access_token == "access-token"
    assert config.thread_key == "mcp"
    assert config.credentials_path == clean_environment


def test_environment_cannot_send_saved_credentials_to_another_server(
    monkeypatch: pytest.MonkeyPatch,
    clean_environment: Path,
) -> None:
    save_credentials(
        clean_environment,
        StoredCredentials(
            app_url="https://saved.example",
            access_token="access-token",
            refresh_token="refresh-token",
            access_token_expires_at=10_000,
            refresh_token_expires_at=20_000,
        ),
    )
    monkeypatch.setenv("ALTHEA_APP_URL", "http://localhost:8080/")
    with pytest.raises(AltheaConfigurationError, match="bound to"):
        runtime_config_from_env()


def test_environment_overrides_runtime_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALTHEA_APP_URL", "http://localhost:8080/")
    monkeypatch.setenv("ALTHEA_PUBLIC_SITE_URL", "http://localhost:3000/")
    monkeypatch.setenv("ALTHEA_THREAD_KEY", "codex:research")
    monkeypatch.setenv("ALTHEA_MCP_HTTP_TIMEOUT", "4.5")
    monkeypatch.setenv("ALTHEA_MCP_POLL_INTERVAL", "0.25")
    monkeypatch.setenv("ALTHEA_MCP_POLL_TIMEOUT", "9")
    monkeypatch.setenv("ALTHEA_MCP_LOG_LEVEL", "debug")

    config = runtime_config_from_env()

    assert config.app_url == "http://localhost:8080"
    assert config.public_site_url == "http://localhost:3000"
    assert config.thread_key == "codex:research"
    assert config.http_timeout == 4.5
    assert config.poll_interval == 0.25
    assert config.poll_timeout == 9
    assert config.log_level == "DEBUG"


@pytest.mark.parametrize(
    ("variable_name", "value", "message"),
    [
        ("ALTHEA_APP_URL", "not-a-url", "Invalid ALTHEA_APP_URL"),
        (
            "ALTHEA_PUBLIC_SITE_URL",
            "not-a-url",
            "Invalid ALTHEA_PUBLIC_SITE_URL",
        ),
        ("ALTHEA_THREAD_KEY", "has spaces", "Invalid ALTHEA_THREAD_KEY"),
        (
            "ALTHEA_MCP_HTTP_TIMEOUT",
            "never",
            "Invalid ALTHEA_MCP_HTTP_TIMEOUT",
        ),
        (
            "ALTHEA_MCP_POLL_INTERVAL",
            "0",
            "Invalid ALTHEA_MCP_POLL_INTERVAL",
        ),
        (
            "ALTHEA_MCP_POLL_TIMEOUT",
            "-1",
            "Invalid ALTHEA_MCP_POLL_TIMEOUT",
        ),
        (
            "ALTHEA_MCP_LOG_LEVEL",
            "verbose",
            "Invalid ALTHEA_MCP_LOG_LEVEL",
        ),
    ],
)
def test_invalid_configuration_fails_clearly(
    monkeypatch: pytest.MonkeyPatch,
    variable_name: str,
    value: str,
    message: str,
) -> None:
    monkeypatch.setenv(variable_name, value)

    with pytest.raises(ValueError, match=message):
        runtime_config_from_env()


def test_retired_api_key_environment_has_setup_instruction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALTHEA_API_KEY", "retired-key")

    with pytest.raises(ValueError, match="althea-mcp setup"):
        runtime_config_from_env()


@pytest.mark.parametrize(
    "app_url",
    [
        "http://althea.example",
        "https://user:password@althea.example",
        "https://althea.example/base",
        "https://:443",
        "https://.",
        "https://example.com:invalid",
        "https://example.com:99999",
        "https://exa mple.com",
        "https://[invalid",
    ],
)
def test_app_url_rejects_unsafe_origins(
    monkeypatch: pytest.MonkeyPatch,
    app_url: str,
) -> None:
    monkeypatch.setenv("ALTHEA_APP_URL", app_url)

    with pytest.raises(ValueError, match="Invalid ALTHEA_APP_URL"):
        runtime_config_from_env()


def test_invalid_app_url_error_does_not_echo_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "ALTHEA_APP_URL",
        "invalid://sensitive-user:sensitive-password@example.com",
    )

    with pytest.raises(ValueError) as error:
        runtime_config_from_env()

    assert "sensitive-user" not in str(error.value)
    assert "sensitive-password" not in str(error.value)


def test_dev_app_uses_dev_public_site(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "ALTHEA_APP_URL",
        "https://althea.dev.tiptreesystems.com",
    )

    config = runtime_config_from_env()

    assert config.public_site_url == "https://dev.tiptreesystems.com"


def test_require_credentials_has_setup_instruction() -> None:
    config = runtime_config_from_env()

    with pytest.raises(ValueError, match="althea-mcp setup"):
        config.require_credentials()
