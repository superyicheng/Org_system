"""Real, safe replay adapter used by the hackathon workflow.

This executes a bundled worker in a separate Python process. It never runs a
command supplied by the browser, which keeps the demo credible and safe.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class RunResult:
    return_code: int
    metrics: dict[str, Any]
    stderr: str


class LocalWorkflowRunner:
    def __init__(self) -> None:
        self.worker = Path(__file__).with_name("workflow_worker.py")

    def environment_fingerprint(self) -> dict[str, str]:
        return {
            "python": platform.python_version(),
            "os": platform.system(),
            "worker_sha256": hashlib.sha256(self.worker.read_bytes()).hexdigest(),
        }

    def launch_and_await(self, payload: dict[str, Any]) -> RunResult:
        completed = subprocess.run(
            [sys.executable, str(self.worker)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=15,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            check=False,
        )
        metrics: dict[str, Any] = {}
        if completed.returncode == 0:
            metrics = json.loads(completed.stdout)
        return RunResult(completed.returncode, metrics, completed.stderr.strip())


def replay_experience(experience: dict[str, Any]) -> dict[str, Any]:
    runner_payload = experience.get("domain_extension", {}).get("runner_payload")
    if not runner_payload:
        raise ValueError("This experience has no safe replay payload.")
    runner = LocalWorkflowRunner()
    result = runner.launch_and_await(runner_payload)
    return {
        "succeeded": result.return_code == 0,
        "observed_metrics": result.metrics,
        "environment_fingerprint": runner.environment_fingerprint(),
        "stderr": result.stderr,
    }
