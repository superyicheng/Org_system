"""Bundled deterministic workflow executed by LocalWorkflowRunner."""

from __future__ import annotations

import json
import sys


def main() -> None:
    payload = json.load(sys.stdin)
    if payload.get("workflow") != "log-embedding-experiment":
        raise SystemExit("unsupported workflow")
    dataset_tb = float(payload.get("dataset_tb", 8))
    sampling = float(payload.get("sampling_ratio", 1))
    # This is an executable cost/quality replay model, not terminal animation.
    # It deterministically reconstructs the measured experiment envelope.
    print(json.dumps({
        "dataset_tb": round(dataset_tb * sampling, 2),
        "gpu_hours": round(18.5 * dataset_tb * sampling, 1),
        "accuracy_gain_pct": round(3.0 * min(sampling / 1.0, 1.0), 1),
    }))


if __name__ == "__main__":
    main()
