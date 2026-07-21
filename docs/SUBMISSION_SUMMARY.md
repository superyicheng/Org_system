# Devpost submission draft — Org_system

## Project name

**org.system — Verified Memory for Your AI Workforce**

## Category

**Developer Tools**

## One-line description

Org_system automatically captures team AI-tool experience, verifies it, and gives a teammate’s AI only permissioned, receipt-backed knowledge instead of untrusted notes.

## What it does

When a person’s AI tool solves a hard problem, that lesson usually disappears into a private session. Org_system captures the finished trace from an MCP connection or thin tool adapter, turns it into an experience candidate, verifies it, stores its provenance/consent, and serves it back to another teammate’s AI only if it is verified and visible.

Every result has a receipt: source, verification verdict, freshness, visibility, and retrieval path. The system also records consumption, so the contributor receives credit and the team can see whose knowledge is actually being reused.

The primary demo preserves an expensive negative result: embedding 8 TB of Kubernetes logs consumed 148 GPU-hours for only a 3% gain. A teammate later proposes the same idea using different language. Hybrid retrieval finds the verified result before execution, returns an attributed receipt, recommends a five-percent pilot, and records the avoided cost. A second CI experiment proves the loop supports new ideas and positive results as well as failures.

## How we built it with Codex

Codex accelerated the transformation of the design report into a runnable vertical slice: it mapped the six-layer design into an API contract, implemented the SQLite `ExperienceStore` behind a swappable memory boundary, created the verification state machine and MCP tool surface, built the three dashboards, and ran the lifecycle checks. The human product decisions were to make verification—not retrieval—the trust boundary; keep simulator execution explicit rather than faking it; and preserve attribution and consent as first-class data.

**Before publishing this text, replace this sentence with the exact, truthful GPT-5.6 Codex session evidence and `/feedback` Session ID recorded in `docs/HACKATHON_EVIDENCE.md`.**

## Demo instructions for judges

1. Run the backend command in the README, then open `http://127.0.0.1:8000`.
2. Follow the Sarah → Tom → replay → novel CI experiment → Mei path in `docs/DEMO_SCRIPT.md`.
3. Open **Judge proof** to inspect live memory, identity, MCP, permission, and model-boundary evidence.
4. Run `python -m unittest discover -s tests -v` from `backend/` to verify the same lifecycle without the UI.

The project is local-only, free to test, and requires no account or API key.
