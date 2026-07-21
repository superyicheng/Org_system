# org.system

**Shared memory for your team's AI.**

Your teammates learn things every day — what worked, what failed, and what it cost. Today
that knowledge stays inside private AI chats and personal notes, so the next person's AI
starts from zero. org.system captures those lessons as work finishes and gives them back
to the whole team's AI, before anyone repeats expensive work.

---

## The problem

Last night Sarah's team finished a GFP promoter screen: a full 96-well plate, six days at
the bench. It failed, because the fluorescence was too noisy to compare the four promoters.

This morning Tom plans the same whole-plate assay. His AI says go ahead, because it has no
idea yesterday happened. The team is about to spend six more lab days learning what it
already knows.

Companies do keep records — wikis, docs, tickets. But someone has to decide the work
mattered, remember it days later, and write it up, and almost nobody does that for the
things that failed. The most expensive lessons are the ones least likely to survive.

## What org.system does

```text
Plan → AI checks team memory → do or adapt the work → AI captures the lesson → verify → the next teammate inherits it
```

1. **Before costly work**, the AI asks org.system whether the team already tried this.
2. **If there is a verified match**, it shows the result, credits the person by name, and
   suggests the cheaper next step.
3. **When the work finishes**, the AI records what happened — including failures, with the
   measured cost.
4. **An administrator verifies the evidence** before teammates can rely on it.

## Why this is different

This is not a shared chat log and not ordinary document search.

- **Nobody has to write it up.** Capture happens at the end of real work, from the session
  itself, while the numbers are still there.
- **Failures are first-class.** A measured dead end is stored as a dead end, with its cost,
  so it can stop someone else. Most tools only keep the wins.
- **Built for the AI to read, not for a human to find.** Each lesson is a structured record
  with evidence, cost, and a reusable next action — not a page someone has to search for.
- **Safe to share across a team.** Similarity only nominates a candidate. Consent,
  visibility, verification, and freshness decide whether another person's AI may use it.
- **Credit follows the knowledge.** Every reuse carries an attribution receipt, so you can
  see whose experience saved whose time.

## Get started

### Try it on your own machine

Requires Python 3.11 or newer.

```bash
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

Open <http://127.0.0.1:8000>. This runs in demo mode with sample data and needs no accounts
or keys. API documentation is at `/docs`.

For real GPT answers, set `OPENAI_API_KEY` before starting. Without it the app falls back to
deterministic wording, so the demo still works.

### Use it with your team

The hosted service is already running:

| | Address | What you get |
| --- | --- | --- |
| **Your organization** | <https://org-system-6hqysxhb3q-uk.a.run.app> | Shared memory with your teammates |
| **Public trial** | <https://org-system-demo-6hqysxhb3q-uk.a.run.app> | A private personal sandbox, isolated from any organization |

1. **Open the website and sign in with Google.**
2. **Create an organization, or join one** with an invite code from a teammate. Everyone in
   an organization shares one memory, and nothing is ever visible across organizations.
3. **Invite your team.** An organization admin creates an invite link from the Organization
   panel and sends it over.
4. **Connect your AI client**, as below.

Admins can review candidate lessons, verify evidence, and remove members from **Trust
center**. By default only allowlisted accounts may sign in; set `ORG_SELF_SERVE=true` to let
any signed-in Google user create or join an organization.

### Connect your AI client

org.system uses OAuth, so there is no token to copy or store. Run one command, approve it in
the browser that opens, and choose the organization the client acts in.

**Claude Code**

```bash
claude mcp add --transport http org_system https://org-system-6hqysxhb3q-uk.a.run.app/mcp/
```

**Codex** — add this to `~/.codex/config.toml`, then run `codex mcp login org_system`:

```toml
[mcp_servers.org_system]
url = "https://org-system-6hqysxhb3q-uk.a.run.app/mcp/"
required = true
enabled_tools = ["avoid_duplicate_work", "recall_experience", "record_completed_work", "capture_session_context"]
default_tools_approval_mode = "writes"

[mcp_servers.org_system.tools.record_completed_work]
approval_mode = "writes"
```

Any MCP-compatible client works with the same URL, because it discovers the OAuth server on
its own. Revoke a connection at any time from the Organization panel.

### Make your AI actually use it

MCP gives your AI the tools. A project instruction file tells it *when* to use them. This
repository ships both, and you should copy the relevant one into your own projects:

- [`AGENTS.md`](AGENTS.md) for Codex
- [`CLAUDE.md`](CLAUDE.md) for Claude Code

They tell the AI to check memory at the start of a session, check again before expensive or
risky work, capture the lesson when work finishes, and say so out loud if org.system is
unreachable instead of pretending it checked.

## The MCP tools

| Tool | What it does |
| --- | --- |
| `avoid_duplicate_work` | Check a proposal against verified team memory before spending anything. |
| `recall_experience` | Retrieve verified, permitted experience with receipts. |
| `capture_session_context` | Turn a finished work session into a structured lesson automatically. |
| `record_completed_work` | Record a known lesson directly. Pass `outcome="failure"` for a measured dead end. |
| `store_experience` | Low-level candidate capture for integrations. |

## What is never stored

Credentials, API keys, personal data, raw private files, and unredacted logs. org.system
stores a redacted, distilled lesson, not your transcripts. It does not scrape your chats,
and capture happens only at task boundaries, with consent.

## For developers

Run the tests from `backend/`:

```bash
python -m unittest discover -s tests -v
```

Where things live:

- `backend/app/main.py` — API routes and orchestration.
- `backend/app/experience_store.py` — storage, organizations, permissions, receipts, recall.
- `backend/app/oauth.py` — OAuth 2.1 authorization server for AI clients.
- `backend/app/mcp_service.py` — the MCP endpoint and its tools.
- `backend/app/distiller.py` and `llm_client.py` — turning sessions into lessons, with a
  deterministic fallback when no API key is set.
- `backend/app/verifiers.py` and `runners.py` — fail-closed verification and replay.
- `frontend/index.html` — the product interface.
- `frontend/authorize.html` — the OAuth consent screen.

Further reading: [deployment](docs/GOOGLE_CLOUD_DEPLOYMENT.md) ·
[live service](docs/LIVE_SERVICE.md) · [demo script](docs/DEMO_SCRIPT.md) ·
[90-second introduction](docs/PITCH_90S.md)

The product name is `org.system`; the repository folder remains `Org_system` for workspace
compatibility.
