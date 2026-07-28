from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from althea_mcp import __version__
from althea_mcp.config import (
    credentials_path_from_env,
    normalize_app_url,
    runtime_config_from_env,
)
from althea_mcp.errors import AltheaError
from althea_mcp.onboarding import run_setup


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="althea-mcp",
        description="Bring your personal Althea into MCP-compatible AI tools.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command")

    setup_parser = subparsers.add_parser(
        "setup",
        help="Sign in or sign up, then save a refreshable session for this machine.",
    )
    setup_parser.add_argument(
        "--app-url",
        help="Althea frontend URL (defaults to ALTHEA_APP_URL or production).",
    )
    setup_parser.add_argument(
        "--credentials-file",
        type=Path,
        help="Override the credentials file location.",
    )
    setup_parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Print access-request URLs without opening a browser.",
    )
    subparsers.add_parser("serve", help="Run the local stdio MCP server.")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "setup":
            config = runtime_config_from_env(validate_saved_credentials=False)
            credentials_path = (
                arguments.credentials_file.expanduser()
                if arguments.credentials_file is not None
                else credentials_path_from_env()
            )
            config = replace(
                config,
                app_url=normalize_app_url(arguments.app_url or config.app_url),
                credentials_path=credentials_path,
            )
            result = asyncio.run(
                run_setup(
                    config,
                    browser_enabled=not arguments.no_browser,
                )
            )
            if not result.configured:
                raise SystemExit(2)
            return

        from althea_mcp.server import main as serve

        serve()
    except (AltheaError, ValueError) as exc:
        parser.exit(1, f"althea-mcp: {exc}\n")
