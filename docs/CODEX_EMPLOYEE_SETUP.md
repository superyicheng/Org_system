# Codex employee setup

Do this on each employee laptop after the shared Google Cloud service is online. There is
no token to create, copy, or store: org.system authenticates over OAuth, and the browser
handles it.

1. Open `https://org-system-6hqysxhb3q-uk.a.run.app` and sign in with the approved Google
   account.
2. Create an organization, or join your team's with an invite link from its administrator.
   Everyone in an organization shares one memory, and nothing is visible across
   organizations.
3. Add the server and sign in to it. The trailing slash on `/mcp/` is intentional.

```bash
codex mcp add org_system --url https://org-system-6hqysxhb3q-uk.a.run.app/mcp/
codex mcp login org_system
```

4. A browser window opens. Approve the connection and choose the organization this laptop
   should act in. The connection is bound to that organization for its lifetime; to use a
   different one, run `codex mcp login org_system` again.
5. Confirm it worked with `codex mcp list`.

Codex can now call `avoid_duplicate_work` before costly work, `capture_session_context` or
`record_completed_work` when work finishes, and `recall_experience` at any point. In the
shared service, completed work is held as a candidate until an administrator verifies the
evidence in Trust center, so Codex never publishes a teammate-visible result by itself.

The behavioural rules that make Codex use these tools consistently live in `AGENTS.md` at
the repository root. Copy it into any other project where you want the same discipline.

## Optional: fail closed

To make a Codex session refuse to start when org.system is unreachable, rather than quietly
working without team memory, add `required = true` under `[mcp_servers.org_system]` in
`~/.codex/config.toml`.

## Revoking a laptop

Run `codex mcp logout org_system` on the laptop, or revoke the connection from the
Organization panel on the website. Revocation takes effect on the next request. Removing
someone from an organization also revokes every connection they hold in it.

The endpoint is standard Streamable HTTP MCP with OAuth discovery, so any MCP-compatible
client can use the same URL. Only the client's own command syntax differs.
