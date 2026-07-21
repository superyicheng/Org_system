import json
import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.distiller import distill
from app.experience_store import ExperienceStore
from app.llm_client import LLMClient
from app.mcp_server import handle
from app.runners import replay_experience
from app.verifiers import verify


class CompleteLoopTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.store = ExperienceStore(Path(self.temporary_directory.name) / "test.sqlite3")
        self.store.seed()

    def tearDown(self) -> None:
        self.store.close()
        self.temporary_directory.cleanup()

    def test_verified_negative_result_prevents_duplicate_gpu_work(self) -> None:
        hits = self.store.recall(
            query="I want semantic search over 30 days of Kubernetes logs using embeddings and GPU compute",
            consumer="Mei",
            limit=3,
            record_usage=True,
        )
        self.assertTrue(hits)
        self.assertEqual(hits[0]["actor"], "Sarah")
        self.assertEqual(hits[0]["verification"]["last_verdict"], "VERIFIED")
        self.assertEqual(hits[0]["resource_evidence"]["gpu_hours"], 148.0)
        self.assertTrue(hits[0]["asset_hash"].startswith("sha256:"))

    def test_replay_executes_bundled_worker_and_reproduces_all_metrics(self) -> None:
        experience = self.store.get("exp-verified-log-embedding")
        replay = replay_experience(experience)
        self.assertTrue(replay["succeeded"])
        self.assertEqual(replay["observed_metrics"]["gpu_hours"], 148.0)
        result = verify(experience, {
            "method": "rerun_and_compare",
            "environment_matches": True,
            "observed_metrics": replay["observed_metrics"],
        })
        self.assertEqual(result["status"], "verified")

    def test_metric_verifier_fails_closed_when_metric_is_missing(self) -> None:
        experience = self.store.get("exp-verified-log-embedding")
        result = verify(experience, {
            "method": "rerun_and_compare",
            "environment_matches": True,
            "observed_metrics": {"gpu_hours": 148.0},
        })
        self.assertEqual(result["status"], "stale")
        self.assertIn("missing", result["verification"]["detail"])

    def test_private_experience_is_only_visible_to_its_origin_title(self) -> None:
        candidate = self.store.create_candidate({
            "actor": "Casey",
            "task": "Rotate a private signing key",
            "trace_summary": "The private key rotation completed.",
            "tool_name": "Codex work session",
            "tags": ["security", "key-rotation"],
            "visibility": "private",
            "consent": True,
        })
        self.store.verify(candidate["id"], verify(candidate, {"method": "outcome_signal", "evidence_confirmed": True}))
        other = self.store.recall(query="private signing key rotation", consumer="Tom", limit=3, record_usage=False)
        owner = self.store.recall(query="private signing key rotation", consumer="Casey", limit=3, record_usage=False)
        self.assertFalse(any(hit["experience_id"] == candidate["id"] for hit in other))
        self.assertTrue(any(hit["experience_id"] == candidate["id"] for hit in owner))

    def test_mock_distiller_preserves_failure_as_reusable_evidence(self) -> None:
        llm = LLMClient(Settings(
            database_url=f"sqlite:///{Path(self.temporary_directory.name) / 'unused.sqlite3'}",
            auth_mode="demo", google_client_id="", google_workspace_domain="",
            admin_emails=frozenset(), allowed_emails=frozenset(), session_secret="", public_url="http://127.0.0.1:8000",
            allowed_origins=("http://127.0.0.1:8000",), llm_mode="mock",
        ))
        result = distill(
            "We embedded 8 TB of Kubernetes logs. It failed as an investment: 148 GPU-hours produced only 3% accuracy gain. Sample first.",
            "Sarah",
            "Codex work session",
            llm,
        )
        self.assertEqual(result["outcome"], "failure")
        self.assertIn("negative-result", result["tags"])
        self.assertEqual(result["resource_evidence"]["gpu_hours"], 148.0)

    def test_stdio_compatible_mcp_surface_exposes_preflight_tool(self) -> None:
        listing = handle(1, "tools/list", {}, self.store)
        names = {tool["name"] for tool in listing["result"]["tools"]}
        self.assertIn("avoid_duplicate_work", names)
        called = handle(2, "tools/call", {
            "name": "avoid_duplicate_work",
            "arguments": {"proposal": "embed Kubernetes logs for semantic search", "consumer": "Mei"},
        }, self.store)
        payload = json.loads(called["result"]["content"][0]["text"])
        self.assertTrue(payload["matched"])
        self.assertEqual(payload["verified_receipts"][0]["actor"], "Sarah")

    def test_semantic_vector_finds_paraphrase_without_exact_keywords(self) -> None:
        hits = self.store.recall(
            query="vectorize a month of cluster diagnostics using accelerator capacity",
            consumer="Tom", limit=3, record_usage=False,
        )
        self.assertTrue(hits)
        self.assertEqual(hits[0]["experience_id"], "exp-verified-log-embedding")
        self.assertGreater(hits[0]["match_breakdown"]["semantic_vector"], 0)

    def test_mcp_records_completed_work_with_server_instructions(self) -> None:
        initialized = handle(1, "initialize", {}, self.store)
        self.assertIn("Before resource-heavy", initialized["result"]["instructions"])
        called = handle(2, "tools/call", {
            "name": "record_completed_work",
            "arguments": {
                "actor": "Mei", "task": "Reduce CI image build time",
                "trace_summary": "Layer cache restored and the measured build passed.",
                "what_worked": "Restore the dependency layer before compilation.",
                "tags": ["ci", "cache"], "evidence_confirmed": True,
            },
        }, self.store)
        payload = json.loads(called["result"]["content"][0]["text"])
        self.assertEqual(payload["status"], "verified")
        self.assertTrue(payload["asset_hash"].startswith("sha256:"))


if __name__ == "__main__":
    unittest.main()
