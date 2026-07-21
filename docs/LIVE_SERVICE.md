# Live service

org.system has two intentionally separate Cloud Run deployments in Google Cloud project `orgsystem-503021`.

## Private organization service

- Web app: `https://org-system-6hqysxhb3q-uk.a.run.app`
- Health check: `https://org-system-6hqysxhb3q-uk.a.run.app/health`
- Streamable HTTP MCP endpoint: `https://org-system-6hqysxhb3q-uk.a.run.app/mcp/`
- Region: `us-east4`
- Database: Cloud SQL PostgreSQL 16 instance `org-system-db`
- Runtime identity: `org-system-run@orgsystem-503021.iam.gserviceaccount.com`

The Cloud Run service is public only for the web shell, health endpoint, Google sign-in configuration, and MCP transport. It protects organizational data with Google session tokens or per-laptop revocable MCP tokens. The admin address `yichengli3869@gmail.com` is the initial team allowlist member; after first sign-in, the boss can add or remove employee email addresses in **Trust center**.

## Public personal-memory trial

- Web app: `https://org-system-demo-6hqysxhb3q-uk.a.run.app`
- Health check: `https://org-system-demo-6hqysxhb3q-uk.a.run.app/health`
- Streamable HTTP MCP endpoint: `https://org-system-demo-6hqysxhb3q-uk.a.run.app/mcp/`
- Cloud Run revision: `org-system-demo-00003-pcz`
- Runtime identity: `org-system-demo-run@orgsystem-503021.iam.gserviceaccount.com`
- Database: the dedicated `orgsystem_public` database on the same Cloud SQL instance, with separate user and Secret Manager credentials

The public trial runs in `AUTH_MODE=public`. Google sign-in creates a persistent personal workspace for any visitor, but every stored experience is forced to private scope and all web, dashboard, and MCP retrieval paths filter to that visitor. It has no access to the private service's database secret or runtime identity. See [PUBLIC_DEMO.md](PUBLIC_DEMO.md) for its visitor flow.

## Google sign-in activation

The deployment intentionally awaits one Google Auth Platform configuration step. Create an OAuth 2.0 **Web application** client in project `orgsystem-503021` and use this exact Authorized JavaScript origin:

```text
https://org-system-6hqysxhb3q-uk.a.run.app
```

No redirect URI is needed for the browser ID-token sign-in flow. Then set its client ID as `GOOGLE_CLIENT_ID` in the Cloud Run service. The client ID is public browser configuration, but never commit generated MCP tokens, the database URL, or the session secret.

## Making the public trial available to everyone

The same OAuth client must additionally include this Authorized JavaScript origin:

```text
https://org-system-demo-6hqysxhb3q-uk.a.run.app
```

Set **Audience** to **External** and publish the OAuth app to **In production**. Testing status only admits listed test users; the public trial uses no sensitive or restricted Google scopes, so basic identity sign-in is sufficient for public visitors.
