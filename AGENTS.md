# org.system — Codex team-memory rules

## Before doing work

- Before resource-heavy, novel, debugging, migration, deployment, or incident work, call the `org_system` MCP tool `avoid_duplicate_work` using the user's natural-language proposal and their visible team name.
- If a verified match is returned, show the attribution receipt and adapt the plan before spending meaningful compute, tokens, or engineering time.
- Never present a candidate, stale, private, or non-consented experience as verified guidance.

## After completing work

- When a task has an objective success/failure signal and the user has consented to team capture, call `record_completed_work` with a redacted trace summary, the reusable lesson, and evidence status.
- Negative results are valuable: record what failed, measured cost, and the safer next experiment.
- Never capture credentials, secrets, raw private files, personal data, or unredacted production logs.

## Repository checks

- Run `python -m unittest discover -s tests -v` from `backend/` after backend changes.
- Keep mock/live boundaries explicit. Retrieval, permissions, persistence, receipts, and verification must remain real in mock mode.
- Preserve the product name `org.system` and the user names Tom, Sarah, and Mei.
