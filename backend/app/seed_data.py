from dataclasses import dataclass


@dataclass(frozen=True)
class SeedSkill:
    id: str
    name: str
    author: str
    created_days_ago: int
    bug_signature: str
    working_code: str
    tags: tuple[str, ...]
    env_assumptions: tuple[str, ...]
    reuse_count: int
    minutes_saved_per_reuse: int
    outcome: str = "success"
    attempted_approach: str = ""
    failure_reason: str = ""
    resource_cost: str = ""
    safe_alternative: str = ""
    stop_conditions: tuple[str, ...] = ()


SEED_SKILLS: tuple[SeedSkill, ...] = (
    SeedSkill(
        id="connect-internal-postgres-v1",
        name="Connect_Internal_Postgres.skill",
        author="Platform Team",
        created_days_ago=45,
        bug_signature=(
            "Internal PostgreSQL connection fails with FATAL: no pg_hba.conf entry, connection timed out, "
            "or connect timeout. The internal database requires the corporate VPN, the internal CA certificate, "
            "and sslmode=verify-full."
        ),
        working_code=r'''#!/usr/bin/env bash
set -euo pipefail

: "${PGHOST:?Set the internal database hostname, for example pg.internal.example.com}"
: "${PGDATABASE:?Set the database name}"
: "${PGUSER:?Set the database user}"
export PGPORT="${PGPORT:-5432}"
export PGSSLMODE="verify-full"
export PGSSLROOTCERT="${PGSSLROOTCERT:-$HOME/.company/certs/internal-postgres-ca.pem}"

if [[ ! -s "$PGSSLROOTCERT" ]]; then
  echo "[Error] Internal CA certificate not found: $PGSSLROOTCERT" >&2
  exit 1
fi

# VPN reachability check. Connect to the corporate VPN before retrying.
if ! timeout 3 bash -c "</dev/tcp/${PGHOST}/${PGPORT}" 2>/dev/null; then
  echo "[Error] Cannot reach ${PGHOST}:${PGPORT}; connect to the corporate VPN first." >&2
  exit 1
fi

pg_isready -h "$PGHOST" -p "$PGPORT" -d "$PGDATABASE" -U "$PGUSER"
psql "host=$PGHOST port=$PGPORT dbname=$PGDATABASE user=$PGUSER sslmode=$PGSSLMODE sslrootcert=$PGSSLROOTCERT" \
  -v ON_ERROR_STOP=1 -c 'select current_database(), current_user, now();'
''',
        tags=("postgres", "ssl", "database", "vpn"),
        env_assumptions=(
            "psql and pg_isready are installed",
            "The user has corporate VPN access",
            "The internal CA certificate is available in a secure local path",
        ),
        reuse_count=12,
        minutes_saved_per_reuse=18,
    ),
    SeedSkill(
        id="refresh-internal-auth-token-v1",
        name="Refresh_Internal_Auth_Token.skill",
        author="Platform Team",
        created_days_ago=60,
        bug_signature=(
            "An internal API returns 401 Unauthorized, token expired, or invalid bearer token even though the request "
            "code is correct. The caller must exchange credentials at the internal token endpoint for a 15-minute token."
        ),
        working_code=r'''#!/usr/bin/env bash
set -euo pipefail

: "${HIVE_CLIENT_ID:?Set HIVE_CLIENT_ID}"
: "${HIVE_CLIENT_SECRET:?Set HIVE_CLIENT_SECRET}"
TOKEN_ENDPOINT="${TOKEN_ENDPOINT:-https://auth.internal.example.com/oauth2/token}"
API_URL="${API_URL:-https://api.internal.example.com/health}"

response="$(curl --fail-with-body --silent --show-error \
  --connect-timeout 5 \
  -X POST "$TOKEN_ENDPOINT" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'grant_type=client_credentials' \
  --data-urlencode "client_id=$HIVE_CLIENT_ID" \
  --data-urlencode "client_secret=$HIVE_CLIENT_SECRET" \
  --data-urlencode 'scope=internal-api')"

export INTERNAL_API_TOKEN="$(jq -er '.access_token' <<<"$response")"
expires_in="$(jq -er '.expires_in // 900' <<<"$response")"
echo "[Auth] Short-lived token acquired for ${expires_in}s. Do not persist or log it."

curl --fail-with-body --silent --show-error \
  -H "Authorization: Bearer $INTERNAL_API_TOKEN" "$API_URL"
''',
        tags=("auth", "token", "api", "401"),
        env_assumptions=(
            "The corporate VPN is connected",
            "curl and jq are installed",
            "The client secret is injected from a local secret manager",
        ),
        reuse_count=9,
        minutes_saved_per_reuse=12,
    ),
    SeedSkill(
        id="fix-pod-crashloop-v1",
        name="Fix_Pod_CrashLoop.skill",
        author="Platform Team",
        created_days_ago=30,
        bug_signature=(
            "A Kubernetes Pod remains in CrashLoopBackOff or ImagePullBackOff with ErrImagePull, pull access denied, "
            "or no basic auth credentials. The namespace is missing the private-registry imagePullSecret."
        ),
        working_code=r'''#!/usr/bin/env bash
set -euo pipefail

: "${NAMESPACE:?Set the Kubernetes namespace}"
: "${DEPLOYMENT:?Set the Deployment name}"
SECRET_NAME="${SECRET_NAME:-internal-registry-pull}"

# Inject Docker config through CI or a secret manager to keep credentials out of shell history.
: "${DOCKER_CONFIG_JSON:?Set the read-only Docker config.json path}"
kubectl -n "$NAMESPACE" create secret generic "$SECRET_NAME" \
  --type=kubernetes.io/dockerconfigjson \
  --from-file=.dockerconfigjson="$DOCKER_CONFIG_JSON" \
  --dry-run=client -o yaml | kubectl apply -f -

# Patch only the target Deployment pod template.
kubectl -n "$NAMESPACE" patch deployment "$DEPLOYMENT" --type=merge \
  -p "{\"spec\":{\"template\":{\"spec\":{\"imagePullSecrets\":[{\"name\":\"$SECRET_NAME\"}]}}}}"
kubectl -n "$NAMESPACE" rollout status deployment/"$DEPLOYMENT" --timeout=120s
kubectl -n "$NAMESPACE" get pods -l "app=$DEPLOYMENT"
''',
        tags=("kubernetes", "pod", "deploy", "secret"),
        env_assumptions=(
            "kubectl is authenticated to the correct cluster context",
            "The operator can create Secrets and patch Deployments in the namespace",
            "Docker config is supplied through a secure channel",
        ),
        reuse_count=7,
        minutes_saved_per_reuse=9,
    ),
    SeedSkill(
        id="avoid-full-log-embedding-v1",
        name="Avoid_Full_Log_Embedding.skill",
        author="Platform Team",
        created_days_ago=62,
        bug_signature=(
            "execution plan production Kubernetes K8s logs 30 days 8 TB full vector embedding semantic index "
            "8 GPU high-resource batch failed experiment"
        ),
        working_code=r'''#!/usr/bin/env bash
set -euo pipefail

# Safe alternative: cluster a one-hour log sample, then embed representative errors only.
NAMESPACE="${NAMESPACE:-platform-prod}"
SAMPLE_WINDOW="${SAMPLE_WINDOW:-1h}"
MAX_EXAMPLES_PER_CLUSTER="${MAX_EXAMPLES_PER_CLUSTER:-5}"

kubectl logs -n "$NAMESPACE" -l app.kubernetes.io/part-of=platform \
  --since="$SAMPLE_WINDOW" --prefix=true > /tmp/hive-log-sample.txt

python scripts/fingerprint_logs.py \
  --input /tmp/hive-log-sample.txt \
  --redact-secrets \
  --max-examples "$MAX_EXAMPLES_PER_CLUSTER" \
  --output /tmp/hive-representative-errors.jsonl

python scripts/embed_representatives.py \
  --input /tmp/hive-representative-errors.jsonl \
  --collection k8s-error-fingerprints-dev \
  --budget-gpu-hours 6
''',
        tags=("kubernetes", "logs", "embedding", "gpu", "cost", "failed-experiment"),
        env_assumptions=(
            "Validate on a redacted one-hour sample first",
            "Do not launch a full 30-day production-log run",
            "Enforce a six-GPU-hour budget cap",
        ),
        reuse_count=2,
        minutes_saved_per_reuse=240,
        outcome="failed",
        attempted_approach="Full vector embedding of 30 days and 8 TB of production Kubernetes logs",
        failure_reason="Excessive duplication; 148 GPU hours produced only a 3% search-accuracy gain",
        resource_cost="148 GPU hours / 19 wall-clock hours",
        safe_alternative="Redact and fingerprint logs, then embed only 3–5 representative samples per cluster",
        stop_conditions=("Logs exceed 1 TB", "Duplicate stack traces exceed 70%", "Small-sample recall is unvalidated"),
    ),
)
