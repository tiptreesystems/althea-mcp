# Contributing to Althea MCP

Thanks for helping improve the public adapter between Althea and local MCP
clients.

## Before opening an issue

Search the existing issues first. For a bug report, include the package version,
operating system, Python version, MCP client, and the smallest useful
reproduction.

Sanitize every log and screenshot. Remove email addresses, messages, OTPs,
access tokens, refresh tokens, and local credential paths. Report
vulnerabilities using [SECURITY.md](SECURITY.md).

## Development setup

```bash
git clone https://github.com/tiptreesystems/althea-mcp.git
cd althea-mcp
uv sync --locked --extra dev
```

Run the core checks from CI:

```bash
uv run ruff check althea_mcp tests
uv run ruff format --check .
uv run pytest -q
uv build
uvx twine check dist/*
```

Tests must use fake `.example` domains and fake credentials. Network calls
belong behind `httpx.MockTransport` unless a test is explicitly designed as a
manual integration check.

## Pull requests

Keep each pull request focused. Explain the user-visible behavior, add or update
tests, and update the README when installation, configuration, authentication,
or tool behavior changes.

The public package should stay independent of private Tiptree packages. Changes
that require a frontend route must remain compatible with the deployed
frontend, or identify the required deployment order clearly.
