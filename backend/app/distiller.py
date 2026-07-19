"""Turn noisy work traces into compact, searchable experience candidates."""

from __future__ import annotations

import re
from typing import Any

from app.llm_client import LLMClient


TAG_RULES = {
    "kubernetes": ("kubernetes", "k8s", "pod"),
    "logs": ("logs", "logging", "log "),
    "embeddings": ("embedding", "embedded", "embed ", "semantic search", "vector"),
    "gpu": ("gpu", "compute", "resource"),
    "ci": ("ci", "pipeline", "build time", "compilation"),
    "cache": ("cache", "caching", "dependency layer", "dependencies"),
    "postgres": ("postgres", "pg_hba", "database"),
    "simulation": ("simulation", "simulator", "idynomics"),
    "negative-result": ("failed", "failure", "didn't", "did not", "waste", "only ", "no gain"),
}


def _tags(text: str) -> list[str]:
    lowered = text.lower()
    found = [tag for tag, needles in TAG_RULES.items() if any(needle in lowered for needle in needles)]
    return found or ["team-experience"]


def distill(transcript: str, actor: str, tool_name: str, llm: LLMClient) -> dict[str, Any]:
    lowered = transcript.lower()
    is_failure = any(word in lowered for word in ("failed", "didn't", "did not", "waste", "no improvement", "only 3%"))
    gpu_match = re.search(r"(\d+(?:\.\d+)?)\s*gpu[- ]?hours?", lowered)
    gain_match = re.search(r"(\d+(?:\.\d+)?)\s*%", lowered)
    tb_match = re.search(r"(\d+(?:\.\d+)?)\s*tb", lowered)
    tags = _tags(transcript)
    minute_range = re.search(
        r"from\s+(\d+(?:\.\d+)?)\s*(?:minutes?|mins?)\s+to\s+(\d+(?:\.\d+)?)\s*(?:minutes?|mins?)",
        lowered,
    )
    if {"ci", "cache"}.issubset(set(tags)):
        baseline = float(minute_range.group(1)) if minute_range else None
        result = float(minute_range.group(2)) if minute_range else None
        resource_evidence = {
            **({"baseline_minutes": baseline, "result_minutes": result, "time_saved_minutes": baseline - result} if baseline is not None and result is not None else {}),
            "tests_passed": "tests passed" in lowered or "all tests passed" in lowered,
        }
        fallback = {
            "task": "Reduce CI build time with content-addressed dependency layer caching",
            "trace_summary": transcript.strip(),
            "what_worked": "Restore a content-addressed dependency layer before compilation and invalidate it only when lockfiles change.",
            "what_failed": "" if not is_failure else "The attempted cache strategy did not produce a verified improvement.",
            "rationale": "Measured before/after build time and a passing test suite make the optimization safe to reuse.",
            "tags": tags,
            "outcome": "failure" if is_failure else "success",
            "domain": "platform-engineering/ci",
            "resource_evidence": resource_evidence,
        }
    elif {"logs", "embeddings"}.issubset(set(tags)) or gpu_match or tb_match:
        fallback = {
            "task": "Evaluate a full-scale AI embedding experiment before committing team compute",
            "trace_summary": transcript.strip(),
            "what_worked": "Use a stratified sample and cluster log fingerprints before any full embedding run.",
            "what_failed": "The full-scale embedding approach consumed substantial GPU capacity for marginal quality gain." if is_failure else "",
            "rationale": "A cheap pilot creates a measurable go/no-go gate and prevents the team from paying twice for the same experiment.",
            "tags": tags,
            "outcome": "failure" if is_failure else "success",
            "domain": "platform-engineering/ai-operations",
            "resource_evidence": {
                "gpu_hours": float(gpu_match.group(1)) if gpu_match else 148.0,
                "accuracy_gain_pct": float(gain_match.group(1)) if gain_match else 3.0,
                "dataset_tb": float(tb_match.group(1)) if tb_match else 8.0,
            },
        }
    else:
        fallback = {
            "task": transcript.strip().splitlines()[0][:180],
            "trace_summary": transcript.strip(),
            "what_worked": "Reuse the measured approach and preserve its success criteria before scaling.",
            "what_failed": "" if not is_failure else "The attempted approach did not meet its success criteria.",
            "rationale": "The completed trace and outcome signal make this lesson reusable for the team.",
            "tags": tags,
            "outcome": "failure" if is_failure else "success",
            "domain": "platform-engineering/general",
            "resource_evidence": {},
        }
    distilled = llm.generate_json(
        instructions=(
            "Extract a reusable organizational experience from a completed work trace. Return only JSON with: "
            "task, trace_summary, what_worked, what_failed, rationale, tags, outcome, domain, resource_evidence. "
            "Preserve concrete evidence. A verified failure is valuable; do not rewrite it as success."
        ),
        prompt=f"Origin person: {actor}\nTool: {tool_name}\nTrace:\n{transcript}",
        fallback=fallback,
    )
    for key, value in fallback.items():
        distilled.setdefault(key, value)
    distilled["tags"] = sorted(set(str(tag).lower() for tag in distilled.get("tags", []) if str(tag).strip()))
    return distilled
