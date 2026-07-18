# Org_system — Phase 0 Build Spec

**The reproducibility-gated experience loop for simulation research groups.**

Status: draft v0.1 · Scope: Phase 0 only (the falsification test) · Product shape: **standalone**

> **Where this fits:** As of the v0.2 design, this document is the **simulation instance (workflow #1)** of the general system described in [`SYSTEM_DESIGN_AND_BUILD_REPORT.md`](./SYSTEM_DESIGN_AND_BUILD_REPORT.md). It is the one workflow with a *strong* verifier (`rerun_and_compare` = reproducibility), used to prove the loop before generalizing. The `SEA` schema here is now the simulation `domain_extension` of the general `experience_asset` schema.

---

## 0. What this document is

This is the concrete build spec for **Phase 0** of Org_system: the single capture → verify → retrieve → reuse loop that the strategy doc's Section 11 calls "the immediate test, before building the general system." It exists to *falsify* the thesis cheaply. We do not build the general system until this one loop provably works.

The strategy doc argues the whole idea down to one wedge: **experience-capture is only as focused as the domain's verification signal is strong**, and simulation is the Tier-1 domain where the verifier is free (a run reproduces or it doesn't). Phase 0 builds exactly that verifier-gated loop, for one asset type, on one real workflow.

**Product shape decision (made):** Org_system is a **standalone** product. It owns its own capture, store, and verification stack rather than shipping as a feature inside an existing simulation/meta-model tool. The one thing it cannot own is the simulator itself — so the simulator is reached through a narrow **`SimulationRunner` adapter** (first target: iDynoMiCS 2). Standalone here means "own architecture + own store + pluggable runner," not "reimplement a physics engine."

---

## 1. The test this spec implements (from strategy §11)

> Take **one asset type** — a converged simulation configuration with its provenance and the reason it works — capture it from **one real workflow**, and verify that a **different person's agent** can retrieve it, that it **reproduces**, and that it **actually gets reused**.

- **Asset type:** `converged_config` (see `schemas/simulation_experience_asset.schema.json`).
- **Workflow:** the iDynoMiCS 2 *Postia placenta* validation run (real, already producing these assets — see `examples/postia_converged_config.sea.json`).
- **Different agent:** a second, clean agent/process with no memory of the original run, given only retrieval access.

### Success criteria (thesis has legs)
1. **Capture is ~free** — the asset is produced as a byproduct of the run, with **≈0 extra human seconds** (a one-line rationale is the only optional human input).
2. **It reproduces** — a second agent re-runs it through the `SimulationRunner` and the verifier returns `REPRODUCED` within tolerance.
3. **It gets reused** — the second agent builds a new run *from* the asset instead of from scratch, and we can measure that it did.

### Kill criteria (rethink before scaling)
- Capture needs **deliberate human effort** → the free-rider problem from §2 is back; stop.
- The asset **does not reproduce** for the next agent → reproducibility-as-governance doesn't hold for this asset type; stop.
- The asset reproduces but **nobody reuses it** → we built a verified graveyard; stop.

Each kill criterion maps to a specific failure the strategy doc predicted (capture incentive, retrieval trust, the graveyard). Phase 0's job is to hit or clear all three, fast.

---

## 2. Architecture (standalone)

Five components + one adapter. Everything is deliberately thin.

```
                      ┌─────────────────────────────────────────────┐
   real run  ───▶     │  CAPTURE HOOK                                │
 (iDynoMiCS 2)        │  wraps the run; on "run judged good",        │
                      │  emits a candidate SEA (config+env+result)   │
                      └───────────────────┬─────────────────────────┘
                                          ▼
                      ┌─────────────────────────────────────────────┐
                      │  ASSET STORE (content-addressed)             │
                      │  SEA json + config blob, indexed             │
                      └───────────────────┬─────────────────────────┘
                                          ▼
                      ┌─────────────────────────────────────────────┐
   SimulationRunner   │  VERIFIER                                    │
   adapter  ◀────────▶│  re-runs the SEA, compares to               │
   (idynomics2)       │  expected_result → verdict, promotes/retires │
                      └───────────────────┬─────────────────────────┘
                                          ▼
                      ┌─────────────────────────────────────────────┐
   second agent ◀────▶│  RETRIEVAL API  +  REUSE HARNESS             │
                      │  query → verified SEA; instantiate new run   │
                      └─────────────────────────────────────────────┘
```

### 2.1 `SimulationRunner` adapter (the standalone seam)
The only interface Org_system needs from any simulator. First and only Phase 0 impl: `idynomics2`.

```
interface SimulationRunner:
    def launch(config_ref, environment) -> RunHandle          # start a run
    def await_result(RunHandle) -> RunResult                  # block/poll to completion
    def extract_metrics(RunResult, metric_specs) -> {name: value}
    def environment_fingerprint() -> {versions..., jar_hash, java, os}
```

Keeping this to four methods is what makes "standalone" cheap: the whole product is runner-agnostic, and adding a second domain later = one new adapter, not a rewrite.

### 2.2 Component responsibilities

| Component | Does | Does **not** |
|---|---|---|
| Capture hook | wrap a run; on a "good" signal, snapshot config + environment fingerprint + measured metrics into a **candidate** SEA | decide correctness; that's the verifier |
| Asset store | content-address the SEA + config blob; small searchable index | run anything |
| Verifier | re-run the SEA via the adapter, compare within tolerance, set verdict + status, schedule re-verify | capture or serve |
| Retrieval API | answer "what do we know about X" with **verified, non-stale** SEAs + provenance + verdict + freshness | return `candidate`/`stale` assets without a loud flag |
| Reuse harness | let a second agent instantiate a new run from a retrieved SEA and record whether it did | judge scientific merit |

---

## 3. The asset schema (core deliverable)

Defined in **`schemas/simulation_experience_asset.schema.json`**, with a worked instance in **`examples/postia_converged_config.sea.json`**. The design principles behind it:

- **Content-addressed & tamper-evident.** `inputs.config_hash` + environment version hashes mean an SEA points at *exact* bytes, so "it reproduces" is a well-defined claim.
- **The claim is separated from the story.** `expected_result.metrics` (machine-checkable, with per-metric `tolerance`) is what the verifier tests. `rationale` (the Polanyi "why it works") *explains* but never *certifies* — it is never trusted on its own. This is the line the graveyard products can't draw because they have no verifier.
- **Lifecycle is first-class.** `status` ∈ {candidate, verified, stale, retired} and `verification.last_verdict` make rot a state transition, not a silent lie. A scheduled re-verify (`reverify_after_days`) is how we prevent "confidently wrong" stale entries — the failure mode §2.3 named.
- **Provenance carries who-knows-what and consent.** `provenance.origin_actor` preserves transactive memory ("who to ask"); `provenance.consent` scopes what capture was allowed (surveillance-tension mitigation, §9).
- **Negative results are the same atom.** A `negative_result` SEA is verified by `rerun_expect_failure` and `links` back to the config it rules out. Phase 0 doesn't build this, but the schema already fits it — that's deliberate, since §3 of the strategy calls negative results the single most valuable unrecorded asset.

---

## 4. The reproducibility gate (verifier contract)

This is the piece that makes Org_system different from every retrieve-only product. The contract:

1. **Reconstruct** the environment via the adapter's `environment_fingerprint()`; if it can't match the SEA's `environment.versions`, verdict = `ENV_BROKEN` (the asset's incantation no longer resolves — a *finding*, not a crash).
2. **Re-run** `inputs.config_ref` through `SimulationRunner.launch → await_result`.
3. **Compare** measured metrics to `expected_result.metrics` under each metric's `tolerance` rule (`rel:x`, `abs:x`, `exact`, `sign`). For `determinism: stochastic`, run `n_repeats` and test the SEA's value against the resulting distribution rather than a point.
4. **Verdict → status:**
   - `REPRODUCED` → status `verified` (trustworthy; serveable).
   - `DIVERGED` → status `stale` (was true, isn't now) + flag for review.
   - `ENV_BROKEN` → status `stale` + capture the environment delta as its own finding.
   - `INCONCLUSIVE` (timeout/nondeterministic beyond tolerance) → stays `candidate`, logged, never served as verified.
5. **Schedule** the next re-verify at `reverify_after_days`. Rot is handled by re-running, not by trusting a timestamp.

**Determinism is the known hard part.** Simulations are often stochastic/floating-point; "reproduces" must mean *tolerance-based equivalence*, never bit-identity. Getting the tolerance policy right for the Postia workflow is itself a Phase 0 deliverable, and it's exactly the kind of judgment that's cheap to calibrate here (we have ground truth) and expensive later in Tier 3 — which is the whole reason the strategy sequences Tier 1 first.

---

## 5. Capture: how it stays free

The single most important design constraint (kill criterion #1). Rules:

- **Instrument the harness, not the human.** The capture hook wraps the run invocation. When a run is tagged good — either a human/agent marks it, or a convergence/validation check auto-fires — the hook snapshots config hash, environment fingerprint, and measured metrics into a candidate SEA. No form to fill.
- **Automatic fields:** everything in `environment`, `inputs`, `expected_result`, and most of `provenance`.
- **The only human touch:** an optional one-line `rationale`. If Phase 0 shows even that one line kills capture, we drop it to zero and let rationale be back-filled later. Capture must survive with zero required human input.

---

## 6. Retrieval & reuse

- **Retrieval API:** query by domain / goal / parameters; returns **verified, non-stale** SEAs first, each with provenance, `last_verdict`, and freshness. `candidate`/`stale` assets are returnable only behind an explicit flag and are never presented as trustworthy. Retrieval trust (§2.4) is solved structurally: what you get back carries its own verification receipt.
- **Reuse harness:** the second agent takes a retrieved SEA and instantiates a *new* run from its config + environment (optionally perturbing parameters). We record: did it start from the asset (vs. scratch)? did the derived run itself reproduce? how long did it take vs. a cold start? Reuse actually happening — not just retrieval succeeding — is success criterion #3.

---

## 7. Metrics that decide pass/fail

| Metric | Target | Kills thesis if |
|---|---|---|
| Human seconds per captured asset | ≈ 0 (≤ one line) | requires real effort |
| Reproduction rate of captured `converged_config` SEAs | high (define exact bar with first runs) | assets don't reproduce |
| Reuse event on a second agent | ≥ 1, real | retrieval works but nobody builds on it |
| Time-to-reuse vs. cold start | meaningfully lower | no time saved |

Instrument these from M0 so the pass/fail call is data, not vibes.

---

## 8. Build order (milestones)

- **M0 — Runner adapter + capture wrapper.** `idynomics2` `SimulationRunner`; wrap one real Postia run; produce a candidate SEA on disk. *(Proves capture is mechanically free.)*
- **M1 — Store + schema validation.** Content-addressed store; validate SEAs against the JSON schema; index for retrieval.
- **M2 — Verifier.** `rerun_and_compare` + the Postia comparator + tolerance policy for stochastic runs; verdict → status transitions; scheduled re-verify. *(Proves reproducibility-as-governance.)*
- **M3 — Retrieval API.** Query → verified SEA with provenance + verdict + freshness; flagged access to non-verified.
- **M4 — Reuse harness + second-agent test.** A clean agent retrieves and instantiates a derived run. *(Proves reuse.)*
- **M5 — Measure & decide.** Collect §7 metrics; make the go/rethink call against §1's success/kill criteria.

Each milestone is independently informative — if M2 shows Postia runs won't reproduce within any sane tolerance, we learn the thesis fails *before* building retrieval.

---

## 9. Open risks & decisions carried forward

- **Consent / surveillance (strategy §11, sharpest risk).** Labs won't let an agent instrument competitive work unless capture is **scoped, inspectable, and opt-in per run**. `provenance.consent` is the schema hook; the *policy* (what's captured by default, what's excluded, who sees it) is a Phase 0 design decision, not an afterthought.
- **Determinism tolerance policy.** The verifier's credibility lives or dies here. Needs the real Postia run to calibrate.
- **First runner adapter target.** Assumed **iDynoMiCS 2** (July-2025 build, driven by its JAR + a protocol XML). Confirm this is the workflow we instrument first.
- **What counts as a "different agent."** Define the isolation boundary for the M4 test so "reproduces for someone else" is honest (no shared caches/memory leaking the answer).
- **Standalone store technology.** Start with content-addressed files + a small local index (SQLite/JSON); keep the store behind an interface so it's not a lock-in bet. Retrieval quality is not the Phase 0 question — the verifier is.

---

## 10. Explicitly out of scope for Phase 0

Multi-agent orchestration, the other four asset kinds, any UI beyond a CLI, cross-team sharing, and the entire Tier-3 verifier-manufacturing thesis. All of it waits behind a passing Phase 0. Building any of it now would be building on an unfalsified premise — which is the exact mistake the strategy doc was written to avoid.
