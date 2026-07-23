"""Public client and MCP adapter for a user's personal Althea."""

from importlib.metadata import PackageNotFoundError, version

from althea_mcp.client import AltheaClient

try:
    __version__ = version("althea-mcp")
except PackageNotFoundError:
    __version__ = "unknown"

__all__ = ["AltheaClient", "__version__"]
