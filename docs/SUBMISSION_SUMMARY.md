# Devpost submission draft — Org_system

## Project name

**Org_system — Verified Experience for Your AI Workforce**

## Category

**Work & Productivity**

## One-line description

Org_system automatically captures team AI-tool experience, verifies it, and gives a teammate’s AI only permissioned, receipt-backed knowledge instead of untrusted notes.

## What it does

When a person’s AI tool solves a hard problem, that lesson usually disappears into a private session. Org_system captures the finished trace from an MCP connection or thin tool adapter, turns it into an experience candidate, verifies it, stores its provenance/consent, and serves it back to another teammate’s AI only if it is verified and visible.

Every result has a receipt: source, verification verdict, freshness, visibility, and retrieval path. The system also records consumption, so the contributor receives credit and the team can see whose knowledge is actually being reused.

Our first workflow is a simulation configuration where correctness is machine-checkable. The `rerun_and_compare` verifier uses tolerance-based metric comparison; the local browser demo makes its fixture status explicit. The same core supports outcome signals, CI tests, and future domain-specific verifiers.

## How we built it with Codex

Codex accelerated the transformation of the design report into a runnable vertical slice: it mapped the six-layer design into an API contract, implemented a PostgreSQL/SQLite `ExperienceStore` behind a swappable memory boundary, created the verification state machine and authenticated Streamable HTTP MCP surface, built the dashboards and Google/Codex onboarding path, and ran lifecycle and transport checks. The human product decisions were to make verification—not retrieval—the trust boundary; keep simulator execution explicit rather than faking it; and preserve attribution and consent as first-class data.

**Before publishing this text, replace this sentence with the exact, truthful GPT-5.6 Codex session evidence and `/feedback` Session ID recorded in `docs/HACKATHON_EVIDENCE.md`.**

## Demo instructions for judges

1. For a no-account demo, run the two commands in the README and open `http://127.0.0.1:8000`. For the team setup, deploy with [Cloud deployment](CLOUD_DEPLOYMENT.md), sign in with Google, and use the in-product Codex connection flow.
2. Click **Capture simulation trace**. The record is a candidate and is not serveable.
3. Click **Run reproducibility check**. It becomes `REPRODUCED`/verified.
4. Click **Recall experience**. Inspect Sarah’s proof receipt and switch to the dashboards.
5. Run `python -m unittest discover -s tests -v` from `backend/` for the same core lifecycle assertion.

The local demo is free to test and requires no account. The shared deployment path uses a hosted PostgreSQL service, Google sign-in, and a personal Codex MCP token per employee.
