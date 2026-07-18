# Judge Q&A

## Is this just RAG over internal documents?

No. Ordinary RAG returns text. Hive.skill stores an operational contract: a fingerprint, environment assumptions, outcome, resource evidence, stop conditions, and executable code. It can produce a fix or block an expensive plan before execution.

## What is actually real in the demo?

ChromaDB persistence and retrieval, similarity scoring, all FastAPI endpoints, optional LLM analysis, and the generated scripts are real. Terminal execution and resource blocking are explicitly simulated.

## Why store failed experiments?

Failures often contain the most expensive organizational knowledge, but they are rarely documented. A failed experiment can save more money than a successful snippet if it prevents an identical large-scale run.

## How do you avoid blocking genuinely new ideas?

Hive shows evidence and similarity rather than issuing a silent denial. The safe default is a capped validation plan, not a permanent prohibition. Engineers can inspect the prior run and proceed after proving the new conditions differ.

## Why use an LLM after vector retrieval?

Vector retrieval finds a candidate. The LLM compares the current conditions with the historical evidence and explains whether the old result actually applies. This reduces keyword-only false positives.

## How would this become production-ready?

Add SSO/RBAC, audit logs, Git-backed skill review, secret scanning, signed scripts, policy-as-code enforcement, real job admission controls, and evaluation datasets for retrieval precision.

## What is the moat?

The accumulated executable failure memory: private environment assumptions, verified fixes, resource outcomes, and stop conditions that generic models and public documentation do not contain.

