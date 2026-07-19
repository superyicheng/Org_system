# Codex employee setup

Do this on each employee laptop after the boss has deployed the shared HTTPS service and configured Google sign-in.

## Connect a laptop

1. Open the hosted Org_system page and sign in with the employee's approved Google account.
2. Click **Create Codex connection**. Copy the token immediately; the server stores only its hash and cannot display it again.
3. Put the token in the laptop's environment, not in a repository.

macOS / Linux (`~/.zshrc` or `~/.bashrc`):

```bash
export ORG_SYSTEM_MCP_TOKEN='orgmcp_replace_with_the_personal_token'
```

Windows PowerShell, for the current user:

```powershell
[Environment]::SetEnvironmentVariable('ORG_SYSTEM_MCP_TOKEN', 'orgmcp_replace_with_the_personal_token', 'User')
```

4. Add this to `~/.codex/config.toml`, using the exact HTTPS URL displayed by Org_system. The trailing slash is intentional.

```toml
[mcp_servers.org_system]
url = "https://your-service.example/mcp/"
bearer_token_env_var = "ORG_SYSTEM_MCP_TOKEN"
required = true
default_tools_approval_mode = "writes"
```

5. Restart Codex so it loads the environment variable and configuration. Ask it to use `org_system.recall_experience` before an unfamiliar task. It can also call `store_experience` after completing work; that makes a candidate, which still requires verification before it can help a teammate.

The configuration uses Codex's remote Streamable HTTP MCP support and `bearer_token_env_var`; see the official [Codex MCP documentation](https://learn.chatgpt.com/docs/extend/mcp).

## Check and revoke

If Codex cannot see the server, confirm the environment variable exists in the process that starts Codex, verify the URL ends in `/mcp/`, and check that the health URL is online. A `401` usually means the token was copied incorrectly or has been revoked.

To retire a laptop, sign in to Org_system on any authorized browser for that user and click **Revoke this connection**. Remove `ORG_SYSTEM_MCP_TOKEN` and the `mcp_servers.org_system` block from that laptop afterward.
