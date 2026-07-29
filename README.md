<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&amp;logoColor=white" alt="Python 3.11+" /></a>
  <a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/MCP-server-7C3AED" alt="MCP server" /></a>
  <a href="https://github.com/tiptreesystems/althea-mcp/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT license" /></a>
</p>

# Althea MCP

Bring your personal [Althea](https://althea.tiptreesystems.com) into Codex,
Claude, and other MCP-compatible tools.

Althea MCP talks to the main Althea application. It uses your existing account
and canonical Althea—with the same dossier and long-term memory you use through
the web, email, SMS, and other channels. It creates a dedicated MCP conversation
thread, just as each other channel has its own thread.

It does **not** use the retired Platform API, create an account in a parallel
auth database, or spin up a separate blank agent.

## Setup

Run one command:

```bash
uvx --from git+https://github.com/tiptreesystems/althea-mcp.git althea-mcp setup
```

The command asks for your email and lets the Althea frontend determine the
correct journey:

- Existing account: Althea emails a verification code.
- Eligible new account: the CLI asks for your name, creates the account, and
  emails a verification code.
- Access still required: the CLI opens the existing Althea access-request page.
  Complete that journey, then rerun the same setup command.

After verification, setup creates a dedicated MCP usage session with a 90-day
refresh lifetime. Its rotating access and refresh tokens are stored at
`~/.config/althea-mcp/credentials.json` with user-only file permissions where
the operating system supports them. Access tokens are refreshed automatically
before they expire; refresh rotation is locked across local MCP processes so
Codex, Claude, and other clients can safely share the credential file. Setup
also schedules the same idempotent profile initialization used after web sign-in.
Optional onboarding details can still be completed in the Althea web app.

When the 90-day session expires or is revoked, a tool call reports that
authentication is required. Rerun `althea-mcp setup` in a separate terminal,
enter the emailed verification code, and retry the call. Running MCP processes
reload the replaced credentials automatically. Credentials from the earlier
API-key format require this one-time setup again; a stale `ALTHEA_API_KEY`
setting is ignored once the new session file exists.

Once the package is on PyPI, the setup command becomes:

```bash
uvx althea-mcp setup
```

## Connect an MCP client

Run setup once before adding the server.

### Codex

```bash
codex mcp add althea -- uvx --from git+https://github.com/tiptreesystems/althea-mcp.git althea-mcp
```

Or add this to `~/.codex/config.toml`:

```toml
[mcp_servers.althea]
command = "uvx"
args = ["--from", "git+https://github.com/tiptreesystems/althea-mcp.git", "althea-mcp"]

[mcp_servers.althea.env]
ALTHEA_THREAD_KEY = "codex"
```

### Claude Code

```bash
claude mcp add --scope user althea -- uvx --from git+https://github.com/tiptreesystems/althea-mcp.git althea-mcp
```

Or add this under the top-level `mcpServers` object in `~/.claude.json`:

```json
{
  "mcpServers": {
    "althea": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/tiptreesystems/althea-mcp.git",
        "althea-mcp"
      ],
      "env": {
        "ALTHEA_THREAD_KEY": "claude-code"
      }
    }
  }
}
```

### Claude Desktop and other local MCP clients

Use the same stdio command:

```json
{
  "mcpServers": {
    "althea": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/tiptreesystems/althea-mcp.git",
        "althea-mcp"
      ]
    }
  }
}
```

Use a distinct `ALTHEA_THREAD_KEY` for each MCP client if you run several
clients concurrently.

## Tools

- `ask_althea(message)`
  Sends a real message to your Althea and waits for her response.
- `send_message_to_althea(message)`
  Sends a message without waiting, for asynchronous requests or context.
- `get_althea_messages(sender=None, limit=10)`
  Retrieves recent messages from the configured MCP thread.

## Configuration

- `ALTHEA_APP_URL`
  Defaults to `https://althea.tiptreesystems.com`. Credentials are bound to
  this URL; rerun setup for the new URL before changing it.
- `ALTHEA_THREAD_KEY`
  Stable conversation-thread identifier. Defaults to `mcp`.
- `ALTHEA_MCP_CREDENTIALS_FILE`
  Overrides `~/.config/althea-mcp/credentials.json`.
- `ALTHEA_MCP_HTTP_TIMEOUT`
  HTTP timeout in seconds. Defaults to `60`.
- `ALTHEA_MCP_POLL_INTERVAL`
  Response polling interval in seconds. Defaults to `2`.
- `ALTHEA_MCP_POLL_TIMEOUT`
  Maximum time `ask_althea` waits for a response. Defaults to `120`.
- `ALTHEA_MCP_LOG_LEVEL`
  Defaults to `WARNING`.

The normal user journey is simply `althea-mcp setup`; no token needs to be
pasted into an MCP config.

## Architecture

This repository is intentionally independent of the private
`tiptree-clients` package. It is a thin public adapter over frontend-owned
routes:

| Capability | Frontend route |
| --- | --- |
| Unified sign-in/sign-up detection | `POST /otp/signin` |
| CLI OTP verification | `POST /mcp/auth/otp/signin/verify` |
| Rotate the MCP usage session | `POST /mcp/auth/token` |
| Idempotent profile initialization | `POST /initialize_profile` |
| Send to the user's Althea | `POST /mcp/threads/{thread_key}/messages` |
| Read the MCP conversation | `GET /mcp/threads/{thread_key}/messages` |

The MCP OTP route asks auth-server for a dedicated usage-session profile.
Auth-server accepts that profile only from the trusted frontend service and
sets an absolute 90-day session-family deadline; ordinary browser session
lifetimes are unchanged. The MCP package sends the current access token to the
frontend, which resolves the main user, provisions or finds that user's
canonical Althea, and owns the MCP `ChannelSession`. The same access token is
used for the corresponding ACTX work; the refresh token never leaves the local
package's token-rotation route.

## Local development

```bash
git clone https://github.com/tiptreesystems/althea-mcp.git
cd althea-mcp
uv sync --extra dev
uv run pytest
uv run ruff check .
uv run althea-mcp setup --app-url http://localhost:8080
```

Running `althea-mcp` with no subcommand starts the stdio MCP server. The
equivalent explicit command is `althea-mcp serve`.

## Distribution

Althea MCP is a local stdio server. It can be published to PyPI and submitted
to the official MCP Registry. Anthropic's connectors directory is for remote
MCP servers, so this local package is not a fit for that directory unless a
hosted transport is added later.

## License

MIT. See the [license](https://github.com/tiptreesystems/althea-mcp/blob/main/LICENSE).
