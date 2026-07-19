# org.system Live Demo Guide

## 1. Start the app

Open PowerShell and run these commands one line at a time:

```powershell
cd C:\Users\BitAltas\Documents\GitHub\Org_system\backend
python -m pip install -r requirements.txt
$env:ORG_SYSTEM_LLM_MODE="mock"
python -m uvicorn app.main:app --reload --port 8000
```

Open `http://127.0.0.1:8000` in a browser.

You can also double-click `START_DEMO.cmd` in the project root. Double-click `STOP_DEMO.cmd` when you finish.

## 2. Thirty-second stage check

1. Click **Reset demo** in the upper-right corner.
2. Confirm that the header says **Team memory online**.
3. Confirm that the people selector is ordered Tom, Sarah, Mei and currently shows Sarah.
4. Use mock mode on stage. Language has a deterministic fallback, while retrieval, persistence, verification, permissions, replay, and impact accounting remain executable.

## 3. Complete 2:55 award demo

### A. Sarah contributes a completed negative result

Select **Sarah**, paste this message, and send it:

```text
We embedded 8 TB of Kubernetes logs for semantic incident search. The completed run consumed 148 GPU-hours but improved accuracy by only 3%. The better path is to sample 5%, cluster recurring log fingerprints, and set a go/no-go quality gate before scaling.
```

Narration: there is no “save knowledge” form. org.system infers that this is completed work, distills the result, verifies its evidence signal, and writes a content-addressed team experience.

### B. Tom proposes similar work using different language

Switch to **Tom**, paste this message, and send it:

```text
I want to vectorize a month of cluster diagnostics using our accelerator capacity. Should I run it at full scale?
```

Narration: Tom did not copy Sarah's wording. The receipt shows a hybrid match and **Semantic vector cosine**, while preserving Sarah's attribution, verification verdict, and SHA-256 receipt.

### C. Replay the evidence

Click **Replay evidence in isolated process**.

You must see:

```text
[SUCCESS] prior result reproduced in an isolated process
```

Narration: this is not terminal animation. The backend starts a separate Python process, regenerates the required metrics, and compares every value. Missing or different evidence fails closed.

### D. Tom proposes a genuinely new experiment

Stay on **Tom** and send:

```text
I want to test content-addressed dependency caching in our CI pipeline. Has the team tried this before?
```

The system should show **No verified prior data**. It allows a bounded experiment with a baseline, measurable success criteria, a cost limit, and a test safety gate. org.system does not block novelty when the team has no precedent.

### E. Tom reports a successful follow-up

Send:

```text
We completed the CI cache experiment. Content-addressed dependency layer caching improved build time from 18 minutes to 7 minutes, and all tests passed. Restore the cache before compilation.
```

The system should automatically capture Tom's positive result, including 18 → 7 minutes, 11 minutes saved, and tests passed.

### F. Mei later inherits Tom's result

Switch to **Mei** and send:

```text
I want to speed up CI builds by caching dependency layers. Should I implement it from scratch?
```

The receipt Origin should be **Tom**. It should show 18 min → 7 min and an avoided duplicate implementation value of 11 min.

### G. Prove that this is an organizational system

Click the top views in this order:

1. **My value** — personal contribution and knowledge-source attribution.
2. **Team map** — who knows what, recorded reuse, intercepted duplicate work, and 148 GPUh avoided. Tom's CI receipt separately records 11 min saved.
3. **Trust center** — verification status, freshness queue, audit events, permission policy, and Codex integration.

## 4. Prove the Codex integration

The project includes `.codex/config.toml` and `AGENTS.md`. Reopen or restart Codex with `C:\Users\BitAltas\Documents\GitHub\Org_system` as a trusted project, then describe a resource-heavy work plan. The project instructions tell Codex to call `avoid_duplicate_work` before meaningful execution.

You can also verify the configuration from a terminal:

```powershell
cd C:\Users\BitAltas\Documents\GitHub\Org_system
codex mcp list
```

If the current Codex session has not reloaded the project-scoped configuration, run:

```powershell
codex mcp add org-system -- python C:\Users\BitAltas\Documents\GitHub\Org_system\backend\mcp_stdio.py
```

## 5. Final verification

Run the backend test suite:

```powershell
cd C:\Users\BitAltas\Documents\GitHub\Org_system\backend
python -m unittest discover -s tests -v
```

Keep the service running, open another terminal, and run:

```powershell
cd C:\Users\BitAltas\Documents\GitHub\Org_system
powershell -ExecutionPolicy Bypass -File .\scripts\smoke-test.ps1
```

## 6. Submission actions only you can complete

- Run `/feedback` in the main Codex task and preserve the real Session ID.
- Record and publish a demo shorter than three minutes.
- Add the real repository and video URLs.
- Make the final Git commit during the eligible submission period.

These submission artifacts cannot be fabricated by the code. Missing them can make an otherwise complete project ineligible or less credible.
