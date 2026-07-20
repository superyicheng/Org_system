import tempfile
import unittest
from pathlib import Path

from app.experience_store import ExperienceStore
from app.verifiers import verify


class ExperienceLifecycleTest(unittest.TestCase):
    def test_candidate_is_not_served_until_verified_then_is_attributed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = ExperienceStore(Path(temporary_directory) / "test.sqlite3")
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
            store.close()


if __name__ == "__main__":
    unittest.main()
