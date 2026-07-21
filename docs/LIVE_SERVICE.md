# Live service

The shared org.system service is deployed in Google Cloud project `orgsystem-503021`.

- Web app: `https://org-system-6hqysxhb3q-uk.a.run.app`
- Health check: `https://org-system-6hqysxhb3q-uk.a.run.app/health`
- Streamable HTTP MCP endpoint: `https://org-system-6hqysxhb3q-uk.a.run.app/mcp/`
- Region: `us-east4`
- Database: Cloud SQL PostgreSQL 16 instance `org-system-db`
- Runtime identity: `org-system-run@orgsystem-503021.iam.gserviceaccount.com`

The Cloud Run service is public only for the web shell, health endpoint, Google sign-in configuration, and MCP transport. It protects organizational data with Google session tokens or per-laptop revocable MCP tokens. The admin address `yichengli3869@gmail.com` is the initial team allowlist member; after first sign-in, the boss can add or remove employee email addresses in **Trust center**.

## Google sign-in activation

The deployment intentionally awaits one Google Auth Platform configuration step. Create an OAuth 2.0 **Web application** client in project `orgsystem-503021` and use this exact Authorized JavaScript origin:

```text
https://org-system-6hqysxhb3q-uk.a.run.app
```

No redirect URI is needed for the browser ID-token sign-in flow. Then set its client ID as `GOOGLE_CLIENT_ID` in the Cloud Run service. The client ID is public browser configuration, but never commit generated MCP tokens, the database URL, or the session secret.
