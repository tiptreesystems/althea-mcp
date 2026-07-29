# Security policy

Althea MCP handles access and refresh tokens for a user's Althea account.
Please report security problems privately.

## Report a vulnerability

Email [martin@tiptreesystems.com](mailto:martin@tiptreesystems.com) with
`althea-mcp security` in the subject. Include:

- The affected version or commit.
- A concise description of the impact.
- Reproduction steps or a minimal proof of concept.
- Any suggested mitigation.

Do not open a public issue for a vulnerability. Never include a live email
verification code, access token, refresh token, credential file, or private
conversation in the report. Use clearly fake values in examples.

If a real credential may have been exposed, stop using it and say so in the
report so the associated session can be revoked.

Security fixes are made on the current `main` branch and included in the next
release.
