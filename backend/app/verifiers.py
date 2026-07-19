"""Pluggable verification rules with fail-closed evidence handling."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def _metric_matches(expected: Any, observed: Any, tolerance: str) -> bool:
    if tolerance == "exact":
        return expected == observed
    if tolerance == "sign":
        return (float(expected) > 0) == (float(observed) > 0)
    if tolerance.startswith("rel:"):
        if float(expected) == 0:
            return float(observed) == 0
        return abs(float(observed) - float(expected)) / abs(float(expected)) <= float(tolerance[4:])
    if tolerance.startswith("abs:"):
        return abs(float(observed) - float(expected)) <= float(tolerance[4:])
    return False


def verify(experience: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    method = request["method"]
    verified_at = datetime.now(UTC).isoformat()
    if method == "outcome_signal":
        # A confirmed failed experiment is a valid, valuable negative result.
        passed = bool(request.get("evidence_confirmed") if request.get("evidence_confirmed") is not None else request.get("outcome_succeeded"))
        verification = {
            "method": method,
            "verdict": "VERIFIED" if passed else "REJECTED",
            "reverify_after_days": 30,
            "detail": "Objective evidence signal confirmed the recorded outcome." if passed else "Objective evidence was not confirmed; kept unverified.",
        }
        if passed:
            verification["verified_at"] = verified_at
        return {
            "status": "verified" if passed else "candidate",
            "verification": verification,
        }

    if method == "tests_ci":
        exit_code = request.get("test_exit_code")
        passed = exit_code == 0
        return {
            "status": "verified" if passed else "candidate",
            "verification": {
                "method": method,
                "verdict": "VERIFIED" if passed else "REJECTED",
                **({"verified_at": verified_at} if passed else {}),
                "reverify_after_days": 14,
                "detail": f"CI/test command exited with code {exit_code}." if exit_code is not None else "No test exit code supplied; verification failed closed.",
            },
        }

    if method == "llm_judge":
        score = request.get("judge_score")
        passed = score is not None and float(score) >= 0.8
        return {
            "status": "verified" if passed else "candidate",
            "verification": {
                "method": method,
                "verdict": "VERIFIED" if passed else "INCONCLUSIVE",
                **({"verified_at": verified_at} if passed else {}),
                "reverify_after_days": 14,
                "detail": f"LLM judge score {float(score):.2f} passed the 0.80 rubric." if passed else "No sufficiently strong LLM judge receipt; kept unverified.",
            },
        }

    if not request.get("environment_matches", True):
        return {
            "status": "stale",
            "verification": {
                "method": "rerun_and_compare",
                "verdict": "STALE",
                "verified_at": verified_at,
                "reverify_after_days": 30,
                "detail": "ENV_BROKEN: runner environment differs from the captured fingerprint.",
            },
        }
    expected_metrics = experience.get("domain_extension", {}).get("expected_metrics", {})
    observed = request.get("observed_metrics", {})
    failures = []
    for name, spec in expected_metrics.items():
        if name not in observed:
            failures.append(f"{name} (missing)")
            continue
        actual = observed[name]
        if not _metric_matches(spec.get("value"), actual, spec.get("tolerance", "exact")):
            failures.append(name)
    reproduced = not failures
    return {
        "status": "verified" if reproduced else "stale",
        "verification": {
            "method": "rerun_and_compare",
            "verdict": "VERIFIED" if reproduced else "STALE",
            "verified_at": verified_at,
            "reverify_after_days": 30,
            "detail": "REPRODUCED: every recorded workflow metric matched within tolerance." if reproduced else f"DIVERGED: metrics diverged: {', '.join(failures)}.",
        },
    }
