# org.system — mandatory team-memory rules for Claude Code

These rules are not optional guidance. Any AI assistant working in this repository
must use the `org_system` MCP tools at the boundaries described below. An assistant
that edits code, plans work, or answers a work question without consulting
organizational memory is operating incorrectly, even if its answer is otherwise good.

`AGENTS.md` carries the same policy for Codex. Keep the two files in agreement when
either one changes.

## Connecting

The server is standard Streamable HTTP MCP, so it is not Codex-specific:

```bash
claude mcp add --transport http org_system https://org-system-6hqysxhb3q-uk.a.run.app/mcp/
```

Confirm with `/mcp`. If the tools are not listed, follow Rule 5 rather than working
around the missing connection.

## Rule 1 — Check memory at the start of the session

On the first substantive request of a session, before planning, searching, or editing,
call `recall_experience` with the user's stated goal.

State the result in one line before continuing:

- `Team memory: N verified receipt(s) — <attribution>` when memory returns something.
- `Team memory: clean — no prior work matched.` when it does not.

Never begin work while silently skipping this step.

## Rule 2 — Check before expensive or risky work

Before resource-heavy, novel, debugging, migration, deployment, or incident work,
call `avoid_duplicate_work` with the user's natural-language proposal. Identity comes
from the connection, so no `consumer` argument is needed over MCP.

- If a verified match is returned, show the attribution receipt and adapt the plan
  before spending meaningful compute, tokens, or engineering time.
- If nothing matches, say so and recommend a bounded experiment. A clean check is a
  licence to proceed, not a reason to stay silent.
- Never present a candidate, stale, private, or non-consented experience as verified
  guidance.

## Rule 3 — Capture completed work

When a task has an objective success or failure signal, ask the user for consent in
plain words, and on approval call `record_completed_work` with a redacted trace
summary, the reusable lesson, and the evidence status.

- Negative results are valuable: record what failed, the measured cost, and the safer
  next experiment. Pass `outcome="failure"` so the dead end is stored as a dead end;
  a failure filed as a success is worse than no record at all.
- In the shared service the record is held as a candidate until an administrator
  verifies it in Trust center. Say this rather than implying the lesson is already
  team-visible.

## Rule 3b — Capture the session itself

For a work session with real detail — commands run, measurements taken, an approach
abandoned — call `capture_session_context` with the redacted session context instead of
hand-writing a summary. The service distils the task, the reusable lesson, the outcome,
and any resource evidence, and files it in your organization.

- Redact before sending. The transcript is the input, so secrets in it become a leak.
- Prefer this over `record_completed_work` when the session is rich; prefer
  `record_completed_work` when you already know the one-line lesson.

## Rule 4 — Never capture these

Credentials, secrets, API keys, personal data, raw private files, and unredacted
production logs must never reach org.system. Redact before recording. If a lesson
cannot be told without a secret, do not record it.

## Rule 5 — Fail loudly, never silently

If org.system is unreachable or returns an error, say so explicitly in the reply and
state that the work is proceeding without a memory check. Do not continue as though
memory had been consulted. A missing check that is announced is recoverable; a missing
check that is hidden corrupts the record of what the team actually knows.

## Repository checks

- Run `python -m unittest discover -s tests -v` from `backend/` after backend changes.
- Keep mock/live boundaries explicit. Retrieval, permissions, persistence, receipts,
  and verification must remain real in mock mode.
- Preserve the product name `org.system` and the user names Tom, Sarah, and Mei.
