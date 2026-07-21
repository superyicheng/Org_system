# org.system

**Verified organizational memory for AI work.**

org.system gives every employee's AI access to the lessons the team has already paid to learn. Before an expensive task begins, the AI checks verified organizational memory for similar work. After a task finishes, it can capture a redacted, evidence-backed lesson for verification and future reuse.

This is not a shared chat history and not ordinary RAG. Similarity finds a candidate; **consent, visibility, verification, and freshness decide whether another employee's AI may use it**.

```text
Employee → AI client → org.system MCP → verified team memory → safer next action
                              ↑                         │
                              └── completed lesson ────┘
```

**OpenAI Build Week track:** Developer Tools

## What problem does it solve?

Important team knowledge often disappears into private AI sessions and individual laptops. A new employee can unknowingly repeat an experiment that a teammate already ran, including expensive failures.

The demo shows the complete loop:

1. Sarah records that embedding 8 TB of Kubernetes logs consumed 148 GPU-hours for only a 3% quality gain.
2. Tom later proposes the same full-scale direction using different words.
3. Before execution, Tom's AI retrieves Sarah's verified negative result, attributes it to Sarah, blocks the full-scale run, and recommends a measured 5% pilot.
4. Tom runs a genuinely new CI experiment and records the successful result.
5. Mei's AI later reuses Tom's verified method instead of rebuilding it from scratch.

The team stops paying for the same lesson twice without preventing novel work.

## Start using org.system as a team

The private organization service is already deployed at:

**[https://org-system-6hqysxhb3q-uk.a.run.app](https://org-system-6hqysxhb3q-uk.a.run.app)**

It runs on Google Cloud Run and uses a shared Cloud SQL PostgreSQL database. Employees do not run a database or expose a service from their laptops.

### 1. The team administrator creates the workspace boundary

1. Open the hosted website.
2. Click **Sign in with Google** using the organization administrator account.
3. Open **Trust center**.
4. Add the Google email addresses of employees who may join the organization.

The administrator can later remove an employee, review candidate experiences, verify evidence, monitor stale knowledge, and revoke MCP connections. Removing an employee invalidates both browser access and personal MCP tokens.

### 2. Each employee signs in to shared memory

1. Open the same hosted website.
2. Click **Sign in with Google** using an allowlisted account.
3. The employee now sees the organization's PostgreSQL-backed memory through their own identity and permission boundary.

Employees share one organizational database, but they do not automatically see every record. Recall still filters by consent, `private` / `team` / `org` visibility, verification status, and freshness.

### 3. Connect Codex or another MCP-compatible AI client

In the signed-in website:

1. Click **Connect Codex**.
2. Enter a label for the laptop.
3. Click **Create personal connection**.
4. Copy or download the setup immediately. The raw token is shown once; org.system stores only its hash.

Store the personal token as an environment variable. Never put it in a repository.

Windows PowerShell:

```powershell
setx ORG_SYSTEM_MCP_TOKEN "orgmcp_replace_with_your_personal_token"
$env:ORG_SYSTEM_MCP_TOKEN = "orgmcp_replace_with_your_personal_token"
```

macOS / Linux:

```bash
export ORG_SYSTEM_MCP_TOKEN='orgmcp_replace_with_your_personal_token'
```

Add the following to the employee's personal `~/.codex/config.toml`. The trailing slash in `/mcp/` is intentional.

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

Restart Codex after saving. Confirm the connection with:

```powershell
codex mcp list
```

The server uses standard Streamable HTTP MCP. Another MCP-compatible AI client can use the same endpoint and personal bearer token; only that client's configuration syntax changes.

### 4. Add the team-memory policy to the AI workflow

MCP provides the tools; the following project instruction makes their use consistent. This repository already includes it in `AGENTS.md`. For another repository, add an equivalent instruction to that project's AI rules:

```text
Before resource-heavy, novel, debugging, migration, deployment, or incident work,
call org_system.avoid_duplicate_work with the natural-language proposal.

After objectively completed work, and only with the user's consent, call
org_system.record_completed_work with a redacted trace summary, reusable lesson,
and evidence status. Never capture secrets, credentials, personal data, raw private
files, or unredacted production logs.
```

### 5. Use AI normally

Once connected, the employee continues working in Codex instead of visiting a separate knowledge-search page for every task.

**Before meaningful work:**

- Codex calls `avoid_duplicate_work` with the planned task.
- org.system performs hybrid lexical and semantic recall.
- If there is a permitted verified match, Codex receives an attribution receipt, prior evidence, and a reusable next action.
- If there is no match, org.system clears the novelty and recommends a bounded experiment rather than blocking innovation.

**After completed work:**

- With employee consent, Codex calls `record_completed_work` at the task boundary.
- org.system stores a redacted task summary, outcome, reusable lesson, evidence signal, contributor identity, and visibility scope.
- In the shared organization service, the new record remains a **candidate** until an administrator verifies it in **Trust center**.
- Only then can it become teammate-visible verified memory.

This is the practical loop:

```text
Plan → pre-flight recall → perform or adapt work → capture result → verify → team reuse
```

## What “automatic capture” means

org.system does **not** indiscriminately scrape entire chats or silently upload every tool call. The AI uses MCP tools at meaningful work boundaries:

- pre-flight recall before costly or risky work;
- consented capture after an objective success or failure;
- a redacted summary rather than raw private context;
- administrator verification before organization-wide reuse.

This preserves the low-friction experience of automatic organizational learning without turning the system into employee surveillance.

## What is stored in organizational memory?

Each experience contains:

- the task goal and domain;
- a redacted trace summary;
- what worked or failed;
- the reusable next action;
- structured evidence and outcome signals;
- contributor attribution and provenance;
- consent and visibility scope;
- verification verdict and re-verification cadence;
- a SHA-256 content receipt;
- attributed reuse events and measured impact.

Candidates, stale records, private records, and non-consented records never appear as verified team guidance.

## Private organization service versus public trial

These are deliberately separate deployments:

| Surface | URL | Memory model |
|---|---|---|
| Private organization | [org-system-6hqysxhb3q-uk.a.run.app](https://org-system-6hqysxhb3q-uk.a.run.app) | Allowlisted employees share permissioned organizational memory |
| Public trial | [org-system-demo-6hqysxhb3q-uk.a.run.app](https://org-system-demo-6hqysxhb3q-uk.a.run.app) | Any Google user gets an isolated private personal memory |

The public trial has a separate database identity and cannot read the private organization's records. See [Live service](docs/LIVE_SERVICE.md) and [Public trial](docs/PUBLIC_DEMO.md).

## What is real?

- Google identity, allowlisted organization membership, and signed browser sessions.
- Shared PostgreSQL persistence in the private Cloud Run deployment.
- Personal, revocable, per-laptop MCP bearer tokens stored as hashes.
- Authenticated Streamable HTTP MCP plus a local stdio fallback.
- Natural-language work intent and completed-result detection.
- Consent-, visibility-, verification-, and freshness-aware retrieval.
- Hybrid lexical and local semantic vectors.
- JSON Schema validation and SHA-256 receipts.
- Verified negative results, attributed reuse, and measured avoided resources.
- Fail-closed metric verification and independent subprocess replay.
- User attribution, team inheritance, Trust center, impact, and Judge proof views.
- Automated lifecycle, permissions, public-isolation, MCP, replay, and API tests.

## Model and demo-safe boundary

- org.system checks permitted, verified organizational memory before generating an answer.
- If a work proposal has no match, it recommends a bounded experiment rather than presenting generic model text as team evidence.
- If the input is a general question and no team memory is used, the backend sends it to the configured OpenAI Responses API model and preserves up to 12 recent conversation turns.
- Completed work still enters the evidence, consent, verification, and memory workflow.
- The UI shows the actual provider used for each general answer. A configured key alone is never displayed as proof that a particular request reached OpenAI.
- Without a key, deterministic English wording keeps the demo reliable.
- Retrieval, persistence, permissions, verification, replay, receipts, MCP contracts, and impact accounting remain executable in both modes.
- The bundled replay worker proves the verifier contract; it is not a production GPU scheduler.
- The application never executes arbitrary browser-supplied shell commands.

## Run locally

Requirements: Python 3.11 or newer.

```powershell
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). API documentation is at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

You can also double-click `START_DEMO.cmd`; use `STOP_DEMO.cmd` when finished.

### Explicit offline mode

```powershell
$env:ORG_SYSTEM_LLM_MODE="mock"
python -m uvicorn app.main:app --reload --port 8000
```

### Enable live GPT answers locally

Keep API keys in environment variables or Secret Manager, never in HTML or Git.

From the repository root, the easiest option is:

```powershell
powershell -ExecutionPolicy Bypass -File .\START_WITH_GPT.ps1
```

The script asks for the API key with hidden input, keeps it only in the backend process environment, selects `gpt-5.6-terra`, and starts the site at [http://127.0.0.1:8000](http://127.0.0.1:8000).

The equivalent manual setup is:

```powershell
# Enter the key privately so it is not saved in shell history.
$secureKey = Read-Host "OpenAI API key" -AsSecureString
$keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
$env:OPENAI_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer)
Remove-Variable secureKey, keyPointer

$env:ORG_SYSTEM_LLM_MODE="openai"
$env:OPENAI_MODEL="gpt-5.6-terra"
cd backend
python -m uvicorn app.main:app --reload --port 8000
```

Open the website and confirm that the badge says `Live GPT · gpt-5.6-terra`. Ask a general question such as `Explain TCP vs UDP with one practical example.` The right-hand receipt must show `GENERAL GPT ANSWER`, an `openai:` provider, and `Memory core · online · checked first`.

The environment variables apply only to the backend started from that PowerShell window. To enable GPT on the hosted Cloud Run website, follow the Secret Manager steps in [Google Cloud deployment](docs/GOOGLE_CLOUD_DEPLOYMENT.md#enable-live-gpt-answers-on-cloud-run).

## Run the award demo

The exact Sarah → Tom → replay → novel experiment → Tom → Mei recording flow is in [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md).

During the final section, open **Judge proof** to show live identity, MCP, storage, permission, model-boundary, and impact evidence. Then open **Team map** to show the real Sarah → Tom and Tom → Mei inheritance links.

## MCP tools

The server exposes four tools. The recommended Codex configuration enables the three needed for normal employee use:

- `avoid_duplicate_work` — check a proposal before meaningful resource spend.
- `recall_experience` — retrieve verified, visible experience with receipts.
- `record_completed_work` — capture an evidence-backed completed lesson for verification.
- `store_experience` — low-level candidate capture for integrations and administration.

See [Codex employee setup](docs/CODEX_EMPLOYEE_SETUP.md) for token lifecycle and revocation.

## Verify the repository

```powershell
cd backend
python -m unittest discover -s tests -v
```

With the server running:

```powershell
powershell -ExecutionPolicy Bypass -File ..\scripts\smoke-test.ps1
```

## API map

- `POST /api/assist` — conversational capture or pre-flight recall.
- `GET /api/ai/status` — sanitized model readiness; never exposes the API key.
- `POST /api/distill` — transcript to candidate experience.
- `POST /api/capture` — explicit structured capture.
- `POST /api/experiences/{id}/verify` — pluggable evidence verification.
- `POST /api/experiences/{id}/replay` — independent workflow replay.
- `POST /api/recall` — verified and permitted recall with attribution.
- `POST /api/gateway/events` — automatic connector task-boundary capture.
- `POST /mcp/` — authenticated Streamable HTTP MCP endpoint.
- `GET /api/dashboard/user/{title}`, `/team`, `/admin`, `/impact` — contribution, discovery, trust, and impact views.
- `GET /api/judge/proof` — sanitized live infrastructure evidence.

## Project map

- `frontend/index.html` — English product and hackathon demo interface.
- `backend/app/main.py` — FastAPI routes and orchestration.
- `backend/app/experience_store.py` — schema-validated memory, permissions, receipts, and recall.
- `backend/app/auth.py` / `mcp_service.py` — Google identity, personal tokens, and remote MCP.
- `backend/app/distiller.py` / `llm_client.py` — live language provider and deterministic fallback.
- `backend/app/verifiers.py` / `runners.py` — fail-closed verification and subprocess replay.
- `backend/mcp_stdio.py` — local Codex-compatible stdio MCP fallback.
- `backend/tests/` — lifecycle and integration tests.
- `docs/LIVE_SERVICE.md` — current private and public deployment details.
- `docs/GOOGLE_CLOUD_DEPLOYMENT.md` — reproducible production deployment.
- `docs/CODEX_EMPLOYEE_SETUP.md` — per-employee connection steps.

The product name is `org.system`; the repository folder remains `Org_system` for workspace compatibility.
