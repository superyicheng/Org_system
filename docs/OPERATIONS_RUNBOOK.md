# Org_system operations runbook

## First-day checklist

1. Deploy the Docker service with a managed PostgreSQL database as described in [Cloud deployment](CLOUD_DEPLOYMENT.md).
2. Configure the production Google web client with the exact hosted origin.
3. Set `AUTH_MODE=google`, `PUBLIC_URL`, `ALLOWED_ORIGINS`, the approved workspace domain, and one or more admin emails.
4. Confirm `/health` reports `auth_mode: google`.
5. Sign in as an admin and as an employee. Verify the employee cannot access `/api/dashboard/admin` and cannot view another employee's private records.
6. Create one Codex connection per employee, then validate a `recall_experience` call from one actual Codex installation.

## Data and access model

- Google identity decides who can use the browser service. The optional Workspace-domain allowlist constrains which accounts can enter.
- An admin is an email in `ORG_SYSTEM_ADMIN_EMAILS`; all other allowed identities are employees.
- Browser sessions are signed and expire after eight hours.
- Codex uses a personal `orgmcp_…` bearer token. PostgreSQL keeps only a SHA-256 hash, an owner, label, creation time, and revocation time.
- Private records are visible to their contributor and admins; team/org records are available only after consent and verification. Recall always excludes candidates and stale records.

## Incident response

If a laptop is lost or a token is pasted somewhere unsafe, revoke it immediately through the signed-in Org_system page. If an admin account is compromised, remove that email from `ORG_SYSTEM_ADMIN_EMAILS`, redeploy/restart the service, and rotate `SESSION_SECRET` to invalidate browser sessions. Rotate the Google OAuth client only if Google credentials are compromised; the browser flow in this build uses the public client ID and validates each Google ID token server-side.
