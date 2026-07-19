import tempfile
import unittest
from pathlib import Path

from app.experience_store import ExperienceStore
from app.config import Settings
from app.auth import new_machine_token, token_digest
from app.verifiers import verify


class ExperienceLifecycleTest(unittest.TestCase):
    def test_candidate_is_not_served_until_verified_then_is_attributed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = ExperienceStore(Settings(
                database_url=f"sqlite:///{Path(temporary_directory) / 'test.sqlite3'}",
                auth_mode="demo", google_client_id="", google_workspace_domain="", admin_emails=frozenset(),
                session_secret="", public_url="http://testserver", allowed_origins=("http://testserver",),
            ))
            candidate = store.create_candidate({
                "actor": "Sarah",
                "task": "Make a simulation grow spatially",
                "trace_summary": "A completed run recorded positive radial growth.",
                "tool_name": "simulation adapter",
                "tags": ["simulation", "spatial-growth"],
                "visibility": "team",
                "consent": True,
                "domain_extension": {"expected_metrics": {"radial_growth": {"value": 1, "tolerance": "sign"}}},
            })
            before = store.recall(query="simulation spatial growth", consumer="Tom", limit=3, record_usage=False)
            self.assertFalse(any(hit["experience_id"] == candidate["id"] for hit in before))
            updated = store.verify(candidate["id"], verify(candidate, {
                "method": "rerun_and_compare", "environment_matches": True,
                "observed_metrics": {"radial_growth": 2}, "outcome_succeeded": True,
            }))
            self.assertEqual(updated["status"], "verified")
            after = store.recall(query="simulation spatial growth", consumer="Tom", limit=3, record_usage=True)
            receipt = next(hit for hit in after if hit["experience_id"] == candidate["id"])
            self.assertEqual(receipt["actor"], "Sarah")
            self.assertEqual(receipt["verification"]["last_verdict"], "VERIFIED")
            self.assertIn("REPRODUCED", receipt["verification"]["details"])

    def test_private_experience_and_mcp_token_are_scoped_to_an_employee(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = ExperienceStore(Settings(
                database_url=f"sqlite:///{Path(temporary_directory) / 'test.sqlite3'}",
                auth_mode="google", google_client_id="client-id", google_workspace_domain="example.com", admin_emails=frozenset(),
                session_secret="long-test-session-secret", public_url="https://org.example", allowed_origins=("https://org.example",),
            ))
            candidate = store.create_candidate({
                "actor": {"id": "sarah@example.com", "display_name": "Sarah"},
                "task": "Keep a private deployment note",
                "trace_summary": "The note contains a private environment-specific observation.",
                "tool_name": "Codex",
                "tags": ["deployment"],
                "visibility": "private",
                "consent": True,
            })
            store.verify(candidate["id"], verify(candidate, {
                "method": "outcome_signal", "environment_matches": True, "outcome_succeeded": True,
            }))
            self.assertFalse(store.recall(query="private deployment", consumer="tom@example.com", limit=3, record_usage=False))
            self.assertTrue(store.recall(query="private deployment", consumer="sarah@example.com", limit=3, record_usage=False))
            store.recall(query="private deployment", consumer="sarah@example.com", limit=3, record_usage=True)
            self.assertEqual(store.verify(candidate["id"], verify(candidate, {
                "method": "outcome_signal", "environment_matches": True, "outcome_succeeded": True,
            }))["status"], "verified")

            store.upsert_user(email="sarah@example.com", display_name="Sarah", role="employee")
            raw_token, _ = new_machine_token()
            token_id = store.create_mcp_token(owner_email="sarah@example.com", label="Sarah laptop", raw_token=raw_token)
            store.upsert_user(email="sarah@example.com", display_name="Sarah Updated", role="employee")
            self.assertEqual(store.identity_for_mcp_token(token_digest(raw_token))["email"], "sarah@example.com")
            self.assertTrue(store.revoke_mcp_token(token_id=token_id, owner_email="sarah@example.com"))
            self.assertIsNone(store.identity_for_mcp_token(token_digest(raw_token)))


if __name__ == "__main__":
    unittest.main()
