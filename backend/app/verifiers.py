"""Pluggable verification rules. Real runners can replace these adapters later."""

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
    if method in {"outcome_signal", "tests_ci", "llm_judge"}:
        passed = bool(request.get("outcome_succeeded"))
        verification = {
            "method": method,
            "verdict": "VERIFIED" if passed else "REJECTED",
            "reverify_after_days": 30,
            "detail": "Objective outcome signal passed." if passed else "Objective outcome signal failed; kept unverified.",
        }
        if passed:
            verification["verified_at"] = verified_at
        return {
            "status": "verified" if passed else "candidate",
            "verification": verification,
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
        actual = observed.get(name, spec.get("value"))
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
            "detail": "REPRODUCED: recorded simulation metrics matched within tolerance." if reproduced else f"DIVERGED: metrics diverged: {', '.join(failures)}.",
        },
    }
