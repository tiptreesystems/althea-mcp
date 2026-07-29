<!-- mcp-name: io.github.tiptreesystems/althea-mcp -->

<p align="center">
  <img src="https://raw.githubusercontent.com/tiptreesystems/althea-mcp/main/assets/banner.svg" alt="Althea MCP. Your personal Althea in local MCP clients." width="100%" />
</p>

<p align="center">
  <a href="https://github.com/tiptreesystems/althea-mcp/actions/workflows/ci.yml"><img src="https://github.com/tiptreesystems/althea-mcp/actions/workflows/ci.yml/badge.svg" alt="CI status" /></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&amp;logoColor=white" alt="Python 3.11+" /></a>
  <a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/MCP-local%20server-638B8D" alt="Local MCP server" /></a>
  <a href="https://github.com/tiptreesystems/althea-mcp/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-2F6D70.svg" alt="MIT license" /></a>
</p>

# Althea MCP

Give Codex, Claude Code, Claude Desktop, and other local MCP clients a direct
line to your personal [Althea](https://althea.tiptreesystems.com).

- **One Althea across every channel.** MCP uses your existing account, profile,
  and long-term memory.
- **Client-specific conversations.** Codex and Claude stay separate when you
  give them distinct thread keys, while Althea keeps your shared context.
- **Fast or asynchronous.** Wait for a reply, leave a message for longer work,
  or read the thread later.
- **Private sign-in.** Authenticate with an emailed code. Your MCP configuration
  contains no API key or pasted token.

> [!IMPORTANT]
> Althea MCP is currently a pre-release. The source is public for review, but
> the production MCP routes are not live yet. Production access will be
> announced with the first tagged release.

[Setup](#setup) · [Connect a client](#connect-an-mcp-client) ·
[First conversation](#start-a-conversation) · [Tools](#tools) ·
[Security and privacy](#security-and-privacy) ·
[Development](#local-development)

## Setup

You need access to Althea and [uv](https://docs.astral.sh/uv/getting-started/installation/).
Until the first PyPI release, install the package directly from GitHub:

```bash
uv tool install git+https://github.com/tiptreesystems/althea-mcp.git
althea-mcp setup
```

If the install succeeds but the command is not found, run `uv tool update-shell`
and open a new terminal.

Run setup yourself in an interactive terminal. Enter your email and verification
code there, not in an AI chat.

```text
Connect your personal Althea
-----------------------------
Email: you@example.com
A verification code was sent to you@example.com.
Verification code:

Althea MCP is ready.
Credentials saved to ~/.config/althea-mcp/credentials.json
```

Setup follows the same account journey as the Althea web app:

- Existing accounts receive a verification code by email.
- Eligible new accounts are asked for a name, then receive a verification code.
- Accounts that still need access are sent to the
  [Althea application](https://tiptreesystems.com/apply). Complete it, then run
  setup again.

The installed server starts without fetching code on every launch. Its tools
still need a network connection to Althea. Upgrade the package later with:

```bash
uv tool upgrade althea-mcp
```

## Connect an MCP client

Complete setup once, then add the local stdio server. Give each client a
different thread key.

> [!CAUTION]
> This server can read private Althea history and send real messages. Register
> it only in clients and projects you trust.

### Codex

```bash
codex mcp add althea \
  --env ALTHEA_THREAD_KEY=codex \
  -- althea-mcp
codex mcp list
```

`codex mcp add` writes to your user configuration. Equivalent
`~/.codex/config.toml`:

```toml
[mcp_servers.althea]
command = "althea-mcp"

[mcp_servers.althea.env]
ALTHEA_THREAD_KEY = "codex"
```

### Claude Code

```bash
claude mcp add althea \
  -e ALTHEA_THREAD_KEY=claude-code \
  -- althea-mcp
claude mcp list
```

That command uses Claude Code's project-local scope. Add `--scope user`
immediately before `althea` only if you want the server available in every
project you open.

A user-wide manual entry under the top-level `mcpServers` object in
`~/.claude.json` looks like this:

```json
{
  "mcpServers": {
    "althea": {
      "type": "stdio",
      "command": "althea-mcp",
      "env": {
        "ALTHEA_THREAD_KEY": "claude-code"
      }
    }
  }
}
```

### Claude Desktop and other local clients

Find the installed command:

```bash
command -v althea-mcp
```

On Windows PowerShell:

```powershell
(Get-Command althea-mcp).Source
```

GUI applications sometimes receive a smaller `PATH` than your terminal. If
`althea-mcp` is not found, use the absolute path returned above:

```json
{
  "mcpServers": {
    "althea": {
      "command": "/absolute/path/to/althea-mcp",
      "env": {
        "ALTHEA_THREAD_KEY": "claude-desktop"
      }
    }
  }
}
```

Restart the client after changing its MCP configuration.

## Start a conversation

Try one of these prompts in your MCP client:

```text
Ask my Althea what I have been working on recently.
```

```text
Send this context to my Althea without waiting for a reply:
I am comparing the two approaches in the current design document.
```

```text
Check whether my Althea has replied in the MCP thread.
```

Messages continue the configured thread. They are real messages to your
personal Althea and may cause her to begin work.

## Tools

| Tool | What it does |
| --- | --- |
| `ask_althea(message)` | Sends a message and uses a 120-second polling window by default for the first reply. If the window expires, the work may still continue. |
| `send_message_to_althea(message)` | Sends a message immediately and returns a receipt without waiting. Use it for context, notes, and longer requests. |
| `get_althea_messages(sender=None, limit=10)` | Returns 1 to 100 recent messages in chronological order. Optionally filter by `user`, `assistant`, or `system`. |

The two send tools are marked as state-changing. Message retrieval is read-only.
The current tool surface is text-only. It does not expose attachments or other
Althea artifacts.

## How it works

```text
Codex / Claude / another MCP client
                │ local stdio
                ▼
           Althea MCP
                │ HTTPS
                ▼
          Althea frontend
                │
                ├── your account, profile, and long-term memory
                └── a persisted conversation for this thread key
```

Althea MCP is a small public adapter. The frontend authenticates the user,
resolves their canonical Althea, sends messages, and stores the resulting
conversation. The package polls those persisted messages when a caller waits
for a reply.

## Sign-in and sessions

Setup creates a normal Althea usage session:

- The access session lasts 7 days.
- Its rotating refresh-token family lasts 14 days from sign-in.
- Access tokens refresh automatically before expiry.
- A cross-process lock lets several local MCP clients share the credential file
  without racing refresh-token rotation.
- When the session expires or is revoked, run `althea-mcp setup` again in a
  separate terminal. Running MCP processes reload the replacement credentials.

Credentials are stored as plaintext JSON at
`~/.config/althea-mcp/credentials.json`. On operating systems that support Unix
file modes, the credential file is set to `0600`. A parent directory created by
Althea MCP is requested as `0700`; check the permissions yourself when using a
pre-existing custom directory.

## Security and privacy

- Messages sent through these tools are persisted in your Althea account, like
  messages from Althea's other channels.
- The local stdio process sends messages and credentials to Althea over HTTPS.
  Even with local transport, conversation data leaves your machine.
- The connected MCP host and model can see tool arguments and replies. They may
  retain that data under their own privacy and retention policies.
- The package sends access credentials only to the Althea origin they were
  issued for. Changing `ALTHEA_APP_URL` requires a new setup.
- The refresh token is sent only to the session rotation endpoint.
- Email verification codes and the credential file are secrets. Never paste
  them into an AI chat, terminal transcript, issue, or pull request.
- To remove the local session, close MCP clients and delete the credential file.
  This forgets the session on that machine. Contact Tiptree if a copied session
  must also be revoked.

Please report vulnerabilities using
[the security policy](https://github.com/tiptreesystems/althea-mcp/security/policy).

## Configuration

Most users only need `althea-mcp setup` and a client-specific thread key.

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `ALTHEA_APP_URL` | `https://althea.tiptreesystems.com` | Althea API origin. Saved credentials are bound to it. Plain HTTP is accepted only for loopback development. |
| `ALTHEA_PUBLIC_SITE_URL` | `https://tiptreesystems.com` | Base URL for terms, privacy, and access requests. Dev Althea selects `https://dev.tiptreesystems.com` automatically. |
| `ALTHEA_THREAD_KEY` | `mcp` | Stable conversation identifier. Use 1 to 128 letters, digits, dots, underscores, colons, or hyphens, starting with a letter or digit. |
| `ALTHEA_MCP_CREDENTIALS_FILE` | `~/.config/althea-mcp/credentials.json` | Override the local credential path. |
| `ALTHEA_MCP_HTTP_TIMEOUT` | `60` | HTTP timeout in seconds. |
| `ALTHEA_MCP_POLL_INTERVAL` | `2` | Delay between response polls in seconds. |
| `ALTHEA_MCP_POLL_TIMEOUT` | `120` | Maximum wait for `ask_althea` in seconds. |
| `ALTHEA_MCP_LOG_LEVEL` | `WARNING` | Python log level. |

Setup also accepts `--credentials-file` to override the credential path and
`--no-browser` to print an access-request URL without opening it.

## Troubleshooting

**`Althea MCP is not configured`**

Run `althea-mcp setup` in a terminal, then restart the MCP client.

**`Your Althea MCP sign-in has expired or was revoked`**

Run setup again. The refresh-token family has a 14-day absolute lifetime.

**Saved credentials are bound to another URL**

Run setup with the same origin the MCP client will use:

```bash
althea-mcp setup --app-url https://althea.example
```

Then set the matching `ALTHEA_APP_URL` in the client configuration.

**`ask_althea` timed out**

Althea may still be working. Call `get_althea_messages` after a short wait.

**The client cannot find `althea-mcp`**

Run `command -v althea-mcp` in a terminal and use that absolute path in the
client configuration.

**Two clients are sharing a conversation**

Assign a distinct `ALTHEA_THREAD_KEY` to each client and restart them.

## Local development

```bash
git clone https://github.com/tiptreesystems/althea-mcp.git
cd althea-mcp
uv sync --locked --extra dev
uv run pytest -q
uv run ruff check althea_mcp tests
uv run ruff format --check .
uv build
uvx twine check dist/*
```

Run setup against a local frontend:

```bash
uv run althea-mcp setup --app-url http://localhost:8080
```

Running `althea-mcp` with no subcommand starts the stdio server. The explicit
equivalent is `althea-mcp serve`.

## Contributing

Bug reports and focused pull requests are welcome. Read
[the contribution guide](https://github.com/tiptreesystems/althea-mcp/blob/main/CONTRIBUTING.md)
before opening one. Remove all email addresses, messages, OTPs, and credentials
from logs and fixtures.

## License

[MIT](https://github.com/tiptreesystems/althea-mcp/blob/main/LICENSE) © Tiptree
Advanced Systems Corporation.
