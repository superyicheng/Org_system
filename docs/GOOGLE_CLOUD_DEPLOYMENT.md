# Google Cloud production deployment

The shared system needs both a backend and a database. This repository is prepared for one Cloud Run service backed by one Cloud SQL for PostgreSQL instance. Employees use the Cloud Run HTTPS URL in their browsers and in Codex; no employee laptop hosts data or opens an inbound port.

## What to create in Google Cloud

Use a new Google Cloud project unless you already have a deliberately shared production project with billing, IAM, and OAuth ownership in place. Enable these APIs in that project:

- Cloud Run Admin
- Cloud Build
- Artifact Registry
- Cloud SQL Admin
- Secret Manager
- Identity Toolkit is **not** required; browser sign-in uses Google Identity Services.

You also need a Google OAuth 2.0 **Web application** client in **APIs & Services → Credentials**. The client ID is safe to put in a Cloud Run environment variable. The OAuth client secret is not used by this browser token-verification flow.

Choose the service name, region, Workspace domain, and admin email before starting:

```bash
export PROJECT_ID="your-new-google-cloud-project"
export REGION="us-east1"
export SERVICE="org-system"
export SQL_INSTANCE="org-system-db"
export DB_NAME="orgsystem"
export DB_USER="orgsystem"
export WORKSPACE_DOMAIN="example.com"
export ADMIN_EMAIL="boss@example.com"
gcloud config set project "$PROJECT_ID"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com sqladmin.googleapis.com secretmanager.googleapis.com
```

## Create the shared database and secrets

Create a PostgreSQL 16 Cloud SQL instance, database, and non-superuser application account. Pick a strong database password and URL-encode it if it contains URL-reserved characters.

```bash
gcloud sql instances create "$SQL_INSTANCE" --database-version=POSTGRES_16 --cpu=1 --memory=3840MiB --region="$REGION"
gcloud sql databases create "$DB_NAME" --instance="$SQL_INSTANCE"
gcloud sql users create "$DB_USER" --instance="$SQL_INSTANCE" --password="REPLACE_WITH_LONG_DATABASE_PASSWORD"
export INSTANCE_CONNECTION_NAME="$(gcloud sql instances describe "$SQL_INSTANCE" --format='value(connectionName)')"
```

Create a `DATABASE_URL` secret using the Cloud SQL Unix socket path, and a separate random session secret. Do not put either value into the repository or a command history that is shared with others.

```bash
printf '%s' "postgresql+psycopg://${DB_USER}:REPLACE_WITH_URL_ENCODED_DATABASE_PASSWORD@/${DB_NAME}?host=/cloudsql/${INSTANCE_CONNECTION_NAME}" | gcloud secrets create org-system-database-url --data-file=-
openssl rand -base64 48 | tr -d '\n' | gcloud secrets create org-system-session-secret --data-file=-
```

Cloud Run's runtime service account needs access to both secrets. For the default compute service account, grant it `roles/secretmanager.secretAccessor`; use your own runtime service account instead if your organization requires it.

This deployment uses a dedicated runtime identity. Grant it only database-connection and secret-read access:

```bash
gcloud iam service-accounts create org-system-run --display-name="org.system Cloud Run"
export RUNTIME_SA="org-system-run@${PROJECT_ID}.iam.gserviceaccount.com"
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:${RUNTIME_SA}" --role="roles/cloudsql.client"
gcloud secrets add-iam-policy-binding org-system-database-url --member="serviceAccount:${RUNTIME_SA}" --role="roles/secretmanager.secretAccessor"
gcloud secrets add-iam-policy-binding org-system-session-secret --member="serviceAccount:${RUNTIME_SA}" --role="roles/secretmanager.secretAccessor"
```

## Deploy Cloud Run, then finish Google sign-in

Create the OAuth web client now. Before the first deployment, add `http://localhost:8000` as a temporary Authorized JavaScript origin. Use the resulting client ID below.

The first Cloud Run deployment needs a placeholder `PUBLIC_URL` only to let the service boot and reveal its generated HTTPS URL. It remains in Google mode, so users cannot gain access until the OAuth origin is configured.

```bash
export GOOGLE_CLIENT_ID="YOUR_WEB_CLIENT_ID.apps.googleusercontent.com"
gcloud run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --allow-unauthenticated \
  --service-account "$RUNTIME_SA" \
  --add-cloudsql-instances "$INSTANCE_CONNECTION_NAME" \
  --set-secrets "DATABASE_URL=org-system-database-url:latest,SESSION_SECRET=org-system-session-secret:latest" \
  --set-env-vars "AUTH_MODE=google,GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID},GOOGLE_WORKSPACE_DOMAIN=${WORKSPACE_DOMAIN},ORG_SYSTEM_ADMIN_EMAILS=${ADMIN_EMAIL},PUBLIC_URL=https://bootstrap.invalid,ALLOWED_ORIGINS=https://bootstrap.invalid,ORG_SYSTEM_LLM_MODE=mock"

export PUBLIC_URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"
echo "$PUBLIC_URL"
```

In the OAuth client's settings, add the exact value of `PUBLIC_URL` as an **Authorized JavaScript origin** (no path and no trailing slash). Then replace the bootstrap values:

```bash
gcloud run services update "$SERVICE" \
  --region "$REGION" \
  --update-env-vars "PUBLIC_URL=${PUBLIC_URL},ALLOWED_ORIGINS=${PUBLIC_URL}"
```

For a custom domain, use that exact HTTPS origin in both the OAuth settings and the two Cloud Run variables after the domain mapping is ready. Do not use a raw IP address or an HTTP origin in production.

## Verify before inviting employees

1. Open `${PUBLIC_URL}/health`; it must report `"status":"ok"`, `"auth_mode":"google"`, and no database errors.
2. Open `${PUBLIC_URL}` in a private browser window. Sign in with an account in the approved Workspace domain.
3. Confirm the configured admin can see **Trust center**, and a regular employee cannot.
4. Click **Connect Codex**, create a personal connection, and follow [Codex employee setup](CODEX_EMPLOYEE_SETUP.md) from a separate laptop.
5. Revoke that test connection in the same dialog and confirm Codex's next request fails with `401`.

The service creates its tables on first connection and seeds the transparent award fixtures only when the database is empty. Use a dedicated empty production database if you do not want those fixtures present.

## Operations

- Keep Cloud SQL automated backups and point-in-time recovery enabled according to your data-retention policy.
- Browser sessions expire after eight hours. Codex tokens remain valid until a user or admin revokes them.
- Use Secret Manager versions to rotate the database URL and session secret, then deploy a new Cloud Run revision.
- Set `OPENAI_API_KEY` as a Cloud Run Secret only if you want live model wording. Retrieval, permissions, persistence, receipts, and verification work without it.
