"""Transparent, local seed data used to make the end-to-end demo runnable."""

from typing import Any


def demo_experiences() -> list[dict[str, Any]]:
    return [
        {
            "id": "exp-postia-spatial-growth",
            "actor": "Sarah",
            "task": "Make the Postia placenta iDynoMiCS 2 validation configuration grow spatially.",
            "trace_summary": "A successful simulation run showed that FungalGrowthManager.updateBody and AgentRelaxation must both be enabled. The result was rerun against recorded output metrics.",
            "source": {"tool_name": "iDynoMiCS 2 runner", "captured_by": "simulation adapter"},
            "content": {
                "claim": "Enable updateBody and AgentRelaxation for nonzero radial expansion.",
                "rationale": "Without both process managers, biomass grows but the colony does not spread spatially.",
            },
            "tags": ["simulation", "idynomics2", "postia", "spatial-growth"],
            "outcome": "success",
            "status": "verified",
            "visibility": {"scope": "team", "consent": True},
            "verification": {
                "method": "rerun_and_compare",
                "last_verdict": "REPRODUCED",
                "last_verified_at": "2026-07-15T14:20:00+00:00",
                "reverify_after_days": 30,
                "details": "Demo fixture matched final_agent_count within rel:0.05 and spatial_expansion sign.",
            },
            "domain_extension": {
                "domain": "idynomics2/fungal-growth",
                "expected_metrics": {
                    "final_agent_count": {"value": 171842, "tolerance": "rel:0.05"},
                    "spatial_expansion": {"value": 1, "tolerance": "sign"},
                },
                "reuse_recipe": "Start from postia_placenta_validation.xml and enable FungalGrowthManager.updateBody + AgentRelaxation.",
            },
            "captured_at": "2026-07-14T10:00:00+00:00",
        },
        {
            "id": "exp-private-pg-connect",
            "actor": "Mei",
            "task": "Connect a local developer environment to internal PostgreSQL.",
            "trace_summary": "The connection failed until the corporate VPN, internal CA, and sslmode=verify-full were configured.",
            "source": {"tool_name": "Claude Code via MCP", "captured_by": "MCP gateway"},
            "content": {
                "claim": "Use corporate VPN, internal CA certificate, and verify-full for internal PostgreSQL.",
                "rationale": "The database rejects unencryped connections and untrusted certificate chains.",
            },
            "tags": ["postgres", "tls", "vpn", "developer-environment"],
            "outcome": "success",
            "status": "verified",
            "visibility": {"scope": "team", "consent": True},
            "verification": {
                "method": "tests_ci",
                "last_verdict": "VERIFIED",
                "last_verified_at": "2026-07-16T09:10:00+00:00",
                "reverify_after_days": 14,
                "details": "Connection smoke test passed in the development environment.",
            },
            "domain_extension": {"domain": "platform-engineering"},
            "captured_at": "2026-07-16T08:40:00+00:00",
        },
        {
            "id": "exp-stale-log-embedding",
            "actor": "Tom",
            "task": "Embed thirty days of production Kubernetes logs for semantic search.",
            "trace_summary": "A full 8 TB run cost 148 GPU hours and produced only a three percent accuracy gain.",
            "source": {"tool_name": "batch runner", "captured_by": "MCP gateway"},
            "content": {
                "claim": "Sample and cluster log fingerprints before a full embedding job.",
                "rationale": "A full embedding run was expensive with negligible improvement.",
            },
            "tags": ["kubernetes", "logs", "embeddings", "negative-result"],
            "outcome": "failed",
            "status": "stale",
            "visibility": {"scope": "team", "consent": True},
            "verification": {
                "method": "outcome_signal",
                "last_verdict": "STALE",
                "last_verified_at": "2026-05-01T00:00:00+00:00",
                "reverify_after_days": 30,
                "details": "Kept for audit, intentionally excluded from verified recall.",
            },
            "domain_extension": {"domain": "platform-engineering"},
            "captured_at": "2026-04-10T12:00:00+00:00",
        },
    ]
