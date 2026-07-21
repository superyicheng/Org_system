import os
import tempfile
import unittest

from fastapi.testclient import TestClient


class APILoopTest(unittest.TestCase):
    def test_veteran_capture_newcomer_preflight_and_real_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            os.environ["ORG_SYSTEM_DB_PATH"] = os.path.join(temporary_directory, "api.sqlite3")
            os.environ["ORG_SYSTEM_LLM_MODE"] = "mock"
            from app.main import app

            with TestClient(app) as client:
                health = client.get("/health")
                self.assertEqual(health.status_code, 200)
                self.assertEqual(health.json()["llm_mode"], "mock")

                proof = client.get("/api/judge/proof")
                self.assertEqual(proof.status_code, 200)
                self.assertEqual(proof.json()["runtime"]["status"], "online")
                self.assertEqual(proof.json()["memory"]["storage_backend"], "SQLite")
                self.assertIn("avoid_duplicate_work", proof.json()["mcp"]["tools"])
                self.assertIn("project-scoped MCP", proof.json()["ai_roles"]["codex"])
                self.assertIn("Candidate", proof.json()["differentiator"]["org_system"])
                self.assertEqual(
                    proof.json()["serve_policy"]["gate"],
                    ["explicit consent", "visibility permission", "verified status"],
                )

                veteran = client.post("/api/assist", json={
                    "role": "auto",
                    "title": "Sarah",
                    "message": "We embedded 8 TB of Kubernetes logs. The run used 148 GPU-hours but produced only 3% accuracy gain. Sample and cluster fingerprints first.",
                })
                self.assertEqual(veteran.status_code, 200)
                self.assertEqual(veteran.json()["experience"]["status"], "verified")
                captured_id = veteran.json()["experience"]["id"]

                newcomer = client.post("/api/assist", json={
                    "role": "auto",
                    "title": "Tom",
                    "message": "I want to embed 30 days of Kubernetes logs for semantic incident search. Should I launch the full GPU job?",
                })
                self.assertEqual(newcomer.status_code, 200)
                payload = newcomer.json()
                self.assertTrue(payload["hit"])
                self.assertEqual(payload["avoided"]["gpu_hours"], 148.0)
                self.assertIn("Sarah", payload["answer"])

                replay = client.post(f"/api/experiences/{captured_id}/replay")
                self.assertEqual(replay.status_code, 200)
                self.assertTrue(replay.json()["serveable"])
                self.assertEqual(replay.json()["replay"]["observed_metrics"]["gpu_hours"], 148.0)

                judge = client.post("/api/experiences/exp-verified-log-embedding/verify/ai")
                self.assertEqual(judge.status_code, 200)
                self.assertGreaterEqual(judge.json()["judge_receipt"]["score"], 0.8)
                self.assertEqual(judge.json()["judge_receipt"]["provider"], "deterministic_mock")

                gateway = client.post("/api/gateway/events", json={
                    "session_id": "codex-session-proof", "event_type": "task_completed",
                    "actor": "Mei", "tool_name": "Codex", "tool_call": "finish service certificate rotation",
                    "result": "Completed the internal service certificate rotation. The TLS smoke test passed.", "succeeded": True,
                    "tags": ["tls", "certificate"],
                })
                self.assertEqual(gateway.status_code, 201)
                self.assertEqual(gateway.json()["experience"]["status"], "verified")

                impact = client.get("/api/dashboard/impact")
                self.assertEqual(impact.status_code, 200)
                self.assertEqual(impact.json()["gpu_hours_avoided"], 148.0)
                self.assertEqual(impact.json()["duplicate_jobs_intercepted"], 1)

                novel = client.post("/api/assist", json={
                    "role": "auto", "title": "Tom",
                    "message": "I want to test content-addressed dependency caching in our CI pipeline. Has the team tried this before?",
                })
                self.assertEqual(novel.status_code, 200)
                self.assertEqual(novel.json()["intent"], "recall")
                self.assertFalse(novel.json()["hit"])
                self.assertIn("no verified prior team experience", novel.json()["answer"].lower())

                completed_ci = client.post("/api/assist", json={
                    "role": "auto", "title": "Tom",
                    "message": "We completed the CI cache experiment. Content-addressed dependency layer caching improved build time from 18 minutes to 7 minutes, and all tests passed. Restore the cache before compilation.",
                })
                self.assertEqual(completed_ci.status_code, 200)
                self.assertEqual(completed_ci.json()["intent"], "capture")
                ci_evidence = completed_ci.json()["experience"]["domain_extension"]["resource_evidence"]
                self.assertEqual(ci_evidence["time_saved_minutes"], 11.0)
                self.assertNotIn("gpu_hours", ci_evidence)

                mei = client.post("/api/assist", json={
                    "role": "auto", "title": "Mei",
                    "message": "I want to speed up CI builds by caching dependency layers. Should I implement it from scratch?",
                })
                self.assertEqual(mei.status_code, 200)
                self.assertTrue(mei.json()["hit"])
                self.assertEqual(mei.json()["receipt"]["actor"], "Tom")
                self.assertEqual(mei.json()["avoided"]["display_value"], "11 min")
                self.assertIn("from 18 to 7 minutes", mei.json()["answer"])

                final_impact = client.get("/api/dashboard/impact")
                self.assertEqual(final_impact.status_code, 200)
                self.assertEqual(final_impact.json()["gpu_hours_avoided"], 148.0)
                self.assertEqual(final_impact.json()["build_minutes_saved"], 11.0)

                team = client.get("/api/dashboard/team")
                self.assertEqual(team.status_code, 200)
                inheritance = team.json()["inheritance_links"]
                self.assertTrue(any(link["source"] == "Sarah" and link["consumer"] == "Tom" for link in inheritance))
                self.assertTrue(any(link["source"] == "Tom" and link["consumer"] == "Mei" for link in inheritance))

            os.environ.pop("ORG_SYSTEM_DB_PATH", None)


if __name__ == "__main__":
    unittest.main()
