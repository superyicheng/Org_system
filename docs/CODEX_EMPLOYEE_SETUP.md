# Codex employee setup

Do this on each employee laptop after the shared Google Cloud service is online.

1. Open `https://org-system-6hqysxhb3q-uk.a.run.app` and sign in with the approved Google account.
2. Click **Connect Codex** and create a connection for that laptop. Copy the token immediately; the server stores only its hash and cannot show it again.
3. Store the token in the laptop environment, never in a repository or a checked-in `.codex/config.toml` file.

macOS / Linux:

```bash
export ORG_SYSTEM_MCP_TOKEN='orgmcp_replace_with_the_personal_token'
```

Windows PowerShell:

```powershell
setx ORG_SYSTEM_MCP_TOKEN "orgmcp_replace_with_the_personal_token"
```

4. Add this block to `~/.codex/config.toml`. The trailing slash is intentional.

```toml
[mcp_servers.org_system]
url = "https://org-system-6hqysxhb3q-uk.a.run.app/mcp/"
bearer_token_env_var = "ORG_SYSTEM_MCP_TOKEN"
required = true
enabled_tools = ["avoid_duplicate_work", "recall_experience", "record_completed_work"]
default_tools_approval_mode = "writes"

[mcp_servers.org_system.tools.record_completed_work]
approval_mode = "writes"
```

5. Restart Codex. It can call `avoid_duplicate_work` before costly work and `record_completed_work` after evidence-backed work completes. In the shared service, completed work is held as a candidate until an administrator verifies the evidence in Trust center; Codex never makes a teammate-visible result by itself.

The **Connect Codex** dialog can also download this setup as a text file. The endpoint uses standard Streamable HTTP MCP, so another MCP-compatible AI client can use the same URL and bearer token; only its client-specific configuration syntax changes.

Each token represents one laptop and one Google identity. To retire a laptop, open **Connect Codex**, press **Revoke** beside that device, then remove the token and MCP configuration from the laptop. Revocation takes effect on the next request.
