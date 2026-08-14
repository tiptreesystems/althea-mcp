from __future__ import annotations

from pathlib import Path
from typing import Any

from althea_mcp import server
from althea_mcp.config import PACKAGE_VERSION, RuntimeConfig
from althea_mcp.credentials import save_credentials
from althea_mcp.models import StoredCredentials


def make_config(tmp_path: Path) -> RuntimeConfig:
    credentials_path = tmp_path / "credentials.json"
    save_credentials(
        credentials_path,
        StoredCredentials(
            app_url="https://althea.example",
            access_token="access-token",
            refresh_token="refresh-token",
            access_token_expires_at=10_000,
            refresh_token_expires_at=20_000,
        ),
    )
    return RuntimeConfig(
        app_url="https://althea.example",
        public_site_url="https://www.althea.example",
        thread_key="codex",
        credentials_path=credentials_path,
        http_timeout=60,
        poll_interval=2,
        poll_timeout=120,
        user_agent="test",
        log_level="WARNING",
    )


def test_create_mcp_registers_five_tools_with_safety_metadata(
    monkeypatch,
    tmp_path: Path,
) -> None:
    class FakeMCP:
        def __init__(self, name: str, **options: Any) -> None:
            self.name = name
            self.options = options
            self.tools: list[Any] = []
            self.annotations: list[Any] = []

        def tool(self, *, annotations: Any) -> Any:
            def register(function: Any) -> Any:
                self.tools.append(function)
                self.annotations.append(annotations)
                return function

            return register

    monkeypatch.setattr(server, "_load_fast_mcp", lambda: FakeMCP)
    monkeypatch.setattr(
        server,
        "_tool_annotations",
        lambda *, read_only: {"read_only": read_only},
    )

    app = server.create_mcp(make_config(tmp_path))

    assert app.name == "althea"
    assert "personal Althea" in app.options["instructions"]
    assert "network of verified ML researchers" in app.options["instructions"]
    assert [tool.__name__ for tool in app.tools] == [
        "ask_althea",
        "send_message_to_althea",
        "get_althea_messages",
        "search_althea_conversations",
        "get_althea_conversation_log",
    ]
    assert app.annotations == [
        {"read_only": False},
        {"read_only": False},
        {"read_only": True},
        {"read_only": True},
        {"read_only": True},
    ]


async def test_real_mcp_discovery_exposes_version_and_annotations(
    tmp_path: Path,
) -> None:
    app = server.create_mcp(make_config(tmp_path))

    initialization = app._mcp_server.create_initialization_options()
    listed_tools = await app.list_tools()

    assert initialization.server_version == PACKAGE_VERSION
    assert [tool.name for tool in listed_tools] == [
        "ask_althea",
        "send_message_to_althea",
        "get_althea_messages",
        "search_althea_conversations",
        "get_althea_conversation_log",
    ]
    assert listed_tools[0].annotations.readOnlyHint is False
    assert listed_tools[0].annotations.idempotentHint is False
    assert listed_tools[2].annotations.readOnlyHint is True
    assert listed_tools[2].annotations.idempotentHint is True
    assert listed_tools[4].annotations.readOnlyHint is True
    assert listed_tools[4].annotations.idempotentHint is True
