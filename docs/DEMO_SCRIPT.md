# Org_system 2:30 demo script

## 0:00–0:20 — problem

“A team pays for the same lesson twice when a successful or failed AI-assisted run dies inside one person’s session. Org_system makes that experience reusable, but only after it earns a verification receipt.”

## 0:20–0:45 — connection and capture

Show the six-stage strip and **Capture simulation trace**.

“A tool adapter or the MCP gateway observes a completed run. Capture is automatic, consent-scoped, and creates a candidate—not a fact other teammates can trust yet.”

## 0:45–1:10 — verification

Show the candidate in Team discovery, then click **Run reproducibility check**.

“For this simulation workflow, the verifier compares rerun metrics to the recorded tolerance. The local demo uses an explicitly labelled fixture; the production adapter would call iDynoMiCS. A pass promotes the candidate to verified; a divergence makes it stale.”

## 1:10–1:40 — teammate reuse

Click **Recall as Tom**.

“Tom’s AI receives only verified experiences he is permitted to see. The returned receipt says Sarah authored it, when it was verified, the verdict, and the activation path. The recall is recorded, so attribution is measurable rather than a claim.”

## 1:40–2:05 — dashboards and MCP

Open **My experience**, **Team discovery**, and **Admin health**.

“The user view separates contribution from consumption. Discovery answers who knows what. Admin health surfaces candidates, stale experiences, visibility, and the re-verification queue. The same API is available to AI tools through the MCP `recall_experience` and `store_experience` tools.”

## 2:05–2:30 — Codex and impact

“I used Codex with GPT-5.6 to turn the design report into this working vertical slice: lifecycle storage, an MCP surface, verifier contracts, the dashboards, and tests. The repository documents the decisions and the submission includes the `/feedback` Session ID from the core build thread. Org_system gives a team’s AI workforce a memory with proof, permissions, and credit.”

Replace the final paragraph only if the session/model evidence in `docs/HACKATHON_EVIDENCE.md` confirms it.
