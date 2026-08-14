from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from althea_mcp.credentials import save_credentials
from althea_mcp.models import StoredCredentials


async def test_installed_command_completes_stdio_handshake(tmp_path: Path) -> None:
    credentials_path = tmp_path / "credentials.json"
    save_credentials(
        credentials_path,
        StoredCredentials(
            app_url="https://althea.example",
            access_token="handshake-access-token",
            refresh_token="handshake-refresh-token",
            access_token_expires_at=time.time() + 3600,
            refresh_token_expires_at=time.time() + 7200,
        ),
    )
    environment = {
        **os.environ,
        "ALTHEA_APP_URL": "https://althea.example",
        "ALTHEA_MCP_CREDENTIALS_FILE": str(credentials_path),
    }
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "althea_mcp"],
        env=environment,
    )

    async with (
        stdio_client(server) as streams,
        ClientSession(*streams) as session,
    ):
        initialization = await session.initialize()
        tools = await session.list_tools()

    assert initialization.serverInfo.name == "althea"
    assert [tool.name for tool in tools.tools] == [
        "ask_althea",
        "send_message_to_althea",
        "get_althea_messages",
        "search_althea_conversations",
        "get_althea_conversation_log",
    ]
