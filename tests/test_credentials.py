from __future__ import annotations

import json
import stat
import traceback
from pathlib import Path

import pytest

from althea_mcp.credentials import load_credentials, save_credentials
from althea_mcp.errors import AltheaConfigurationError
from althea_mcp.models import StoredCredentials


def test_credentials_round_trip_with_user_only_permissions(tmp_path: Path) -> None:
    credentials_path = tmp_path / "nested" / "credentials.json"
    credentials = StoredCredentials(
        app_url="https://althea.example",
        access_token="access-token",
        refresh_token="refresh-token",
        access_token_expires_at=10_000,
        refresh_token_expires_at=20_000,
    )

    save_credentials(credentials_path, credentials)

    assert load_credentials(credentials_path) == credentials
    assert stat.S_IMODE(credentials_path.stat().st_mode) == 0o600
    stored_payload = credentials_path.read_text(encoding="utf-8")
    assert "access-token" in stored_payload
    assert "refresh-token" in stored_payload


def test_missing_credentials_returns_none(tmp_path: Path) -> None:
    assert load_credentials(tmp_path / "missing.json") is None


def test_retired_credentials_fail_with_setup_instruction(tmp_path: Path) -> None:
    credentials_path = tmp_path / "credentials.json"
    credentials_path.write_text(
        json.dumps(
            {
                "version": 1,
                "app_url": "https://althea.example",
                "api_key": "retired-key",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(AltheaConfigurationError, match="althea-mcp setup"):
        load_credentials(credentials_path)


def test_invalid_credentials_do_not_echo_tokens(tmp_path: Path) -> None:
    credentials_path = tmp_path / "credentials.json"
    credentials_path.write_text(
        json.dumps(
            {
                "version": 2,
                "app_url": "https://althea.example",
                "access_token": "sensitive-access-token",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(AltheaConfigurationError) as error:
        load_credentials(credentials_path)

    assert "sensitive-access-token" not in str(error.value)
    formatted_traceback = "".join(traceback.format_exception(error.value))
    assert "sensitive-access-token" not in formatted_traceback
    assert error.value.__cause__ is None
