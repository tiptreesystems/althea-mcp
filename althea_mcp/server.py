from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from althea_mcp.client import AltheaClient
from althea_mcp.config import PACKAGE_VERSION, RuntimeConfig, runtime_config_from_env
from althea_mcp.tools import AltheaTools

SERVER_INSTRUCTIONS = (
    "This server connects to the user's personal Althea and uses the same "
    "account, profile, and long-term memory available through Althea's other "
    "channels. Each configured thread key has its own conversation. Calls that "
    "send messages are real communications to Althea and may cause her to begin "
    "work. Use ask_althea when an immediate reply is needed, "
    "send_message_to_althea for asynchronous updates or requests, and "
    "get_althea_messages to inspect the MCP thread."
)


def _load_fast_mcp() -> Any:
    from mcp.server.fastmcp import FastMCP

    return FastMCP


def _tool_annotations(*, read_only: bool) -> Any:
    from mcp.types import ToolAnnotations

    return ToolAnnotations(
        readOnlyHint=read_only,
        destructiveHint=False,
        idempotentHint=read_only,
        openWorldHint=True,
    )


def _set_server_version(app: Any) -> None:
    low_level_server = getattr(app, "_mcp_server", None)
    if low_level_server is not None:
        low_level_server.version = PACKAGE_VERSION


def _client_lifespan(client: AltheaClient) -> Any:
    @asynccontextmanager
    async def lifespan(_server: Any) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await client.close()

    return lifespan


def create_mcp(
    config: RuntimeConfig | None = None,
    *,
    client: AltheaClient | None = None,
) -> Any:
    runtime_config = config or runtime_config_from_env()
    if client is None:
        runtime_config.require_credentials()
        althea_client = AltheaClient(
            app_url=runtime_config.app_url,
            credentials_path=runtime_config.credentials_path,
            timeout=runtime_config.http_timeout,
            user_agent=runtime_config.user_agent,
        )
    else:
        althea_client = client
    tool_implementations = AltheaTools(althea_client, runtime_config)

    fast_mcp = _load_fast_mcp()
    app = fast_mcp(
        "althea",
        instructions=SERVER_INSTRUCTIONS,
        lifespan=_client_lifespan(althea_client),
        log_level=runtime_config.log_level,
    )
    _set_server_version(app)
    app.tool(annotations=_tool_annotations(read_only=False))(tool_implementations.ask_althea)
    app.tool(annotations=_tool_annotations(read_only=False))(
        tool_implementations.send_message_to_althea
    )
    app.tool(annotations=_tool_annotations(read_only=True))(
        tool_implementations.get_althea_messages
    )
    return app


def main() -> None:
    try:
        app = create_mcp()
    except ModuleNotFoundError as exc:
        if exc.name == "mcp" or (exc.name is not None and exc.name.startswith("mcp.")):
            raise SystemExit(
                "Missing MCP dependency. Install the project before running it."
            ) from exc
        raise
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    app.run(transport="stdio")


if __name__ == "__main__":
    main()
