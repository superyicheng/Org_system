"""End-to-end team-memory test built on a SYNTHETIC iGEM promoter-screen fixture.

The plate readings here are SIMULATED, not measured. They are generated from an
explicit noise model (biomass spread, plate-edge evaporation, a thermal gradient,
and unsubtracted media autofluorescence) so that the failure this test describes is
*derived* rather than asserted: the raw coefficient of variation lands near 38%
because the model says it must, and it drops under the 15% go/no-go gate once
blanks are subtracted and fluorescence is normalised to OD600.

Nothing here is a measurement claim. The records it writes live in a throwaway
SQLite file, carry the `synthetic-fixture` tag, and never reach a deployed store.

The underlying lesson being exercised is real and was supplied by the team:
a 96-well GFP promoter screen consumed six wet-lab days and could not rank
promoters because the readings were uncalibrated.
"""

from __future__ import annotations

import json
import random
import statistics
import tempfile
import unittest
from pathlib import Path

from app.experience_store import ExperienceStore
from app.mcp_server import handle
from app.verifiers import verify


ROWS = "ABCDEFGH"

# Real Anderson-collection parts with distinct published relative activities.
# Distinct values matter: tied strengths would make "correct ranking" ambiguous.
PROMOTER_STRENGTH = {
    "J23100": 1.00, "J23101": 0.70, "J23106": 0.47, "J23107": 0.36,
    "J23110": 0.33, "J23105": 0.24, "J23116": 0.16, "J23113": 0.01,
}

# Noise model. Tuned once so the raw CV reproduces the recorded 38%; see docstring.
PLATE_MODEL = {
    "seed": 7,
    "base_od": 0.62,
    "od_log_sigma": 0.38,      # colony-to-colony biomass spread
    "edge_penalty": 0.35,      # perimeter wells evaporate and under-grow
    "column_gradient": 0.35,   # thermal/evaporation gradient along the long axis
    "blank_mean": 780.0,       # media + instrument autofluorescence
    "blank_log_sigma": 0.45,
    "reader_gain": 42000.0,
    "read_log_sigma": 0.06,
}

CV_GATE_PERCENT = 15.0


def cv_percent(values: list[float]) -> float:
    return 100.0 * statistics.stdev(values) / statistics.mean(values)


def _well(rng: random.Random, row: str, column: int, promoter: str) -> dict[str, object]:
    model = PLATE_MODEL
    on_edge = column in (1, 12) or row in ("A", "H")
    gradient = 1.0 - model["column_gradient"] * (column - 1) / 11.0
    od600 = (
        model["base_od"] * gradient
        * (1.0 - model["edge_penalty"] if on_edge else 1.0)
        * rng.lognormvariate(0.0, model["od_log_sigma"])
    )
    autofluorescence = model["blank_mean"] * rng.lognormvariate(0.0, model["blank_log_sigma"])
    signal = model["reader_gain"] * PROMOTER_STRENGTH[promoter] * od600 * rng.lognormvariate(0.0, model["read_log_sigma"])
    return {
        "well": f"{row}{column:02d}",
        "promoter": promoter,
        "od600": round(od600, 4),
        "raw_fluorescence": round(autofluorescence + signal, 1),
        "_autofluorescence": autofluorescence,
    }


def uncalibrated_screen() -> list[dict[str, object]]:
    """The run that failed: 96 sample wells, one promoter per row, no blanks.

    One promoter per row is the design flaw. It confounds promoter identity with
    row position, so the plate's edge and gradient effects are inseparable from
    the biology the screen is trying to measure.
    """
    rng = random.Random(PLATE_MODEL["seed"])
    return [
        _well(rng, row, column, list(PROMOTER_STRENGTH)[index])
        for index, row in enumerate(ROWS)
        for column in range(1, 13)
    ]


def calibrated_pilot() -> dict[str, object]:
    """The recommended replacement: 12 wells — 3 blanks + 3 promoters x 3 replicates.

    Replicates are scattered across interior wells instead of sharing a row, so
    position effects average out rather than loading onto one promoter.
    """
    rng = random.Random(PLATE_MODEL["seed"] + 1)
    interior = [(row, column) for row in "BCDEFG" for column in range(2, 12)]
    rng.shuffle(interior)
    chosen = iter(interior)

    blanks = []
    for _ in range(3):
        row, column = next(chosen)
        blanks.append({
            "well": f"{row}{column:02d}",
            "promoter": "BLANK",
            "od600": 0.0,
            "raw_fluorescence": round(PLATE_MODEL["blank_mean"] * rng.lognormvariate(0.0, PLATE_MODEL["blank_log_sigma"]), 1),
        })

    samples = []
    for promoter in ("J23100", "J23106", "J23110"):
        for _ in range(3):
            row, column = next(chosen)
            well = _well(rng, row, column, promoter)
            # Biological replicates are separate colonies, so they carry their own spread.
            well["raw_fluorescence"] = round(float(well["raw_fluorescence"]) * rng.lognormvariate(0.0, 0.08), 1)
            samples.append(well)
    return {"blanks": blanks, "samples": samples}


def detection_limit(blank_readings: list[float]) -> float:
    """Blank mean + 3 SD — below this a promoter cannot be ranked, only called dark."""
    return statistics.mean(blank_readings) + 3.0 * statistics.stdev(blank_readings)


def normalised_units(wells: list[dict[str, object]], blank_mean: float) -> dict[str, list[float]]:
    grouped: dict[str, list[float]] = {}
    for well in wells:
        value = (float(well["raw_fluorescence"]) - blank_mean) / float(well["od600"])
        grouped.setdefault(str(well["promoter"]), []).append(value)
    return grouped


def grouped_raw(wells: list[dict[str, object]]) -> dict[str, list[float]]:
    grouped: dict[str, list[float]] = {}
    for well in wells:
        grouped.setdefault(str(well["promoter"]), []).append(float(well["raw_fluorescence"]))
    return grouped


SCREEN_LESSON = {
    "task": "Screen the iGEM Anderson GFP promoter library across a 96-well plate to rank promoter strength",
    "trace_summary": (
        "All 96 wells were read after six wet-lab days. The plate carried no blank wells and no OD600 "
        "normalisation, so promoter identity was confounded with row position. Pooled replicate CV on raw "
        "fluorescence was 38%, which is wider than the spacing between adjacent Anderson parts, so the "
        "library could not be ranked. Re-reading the same plate cannot recover the missing calibration."
    ),
    "reuse_recipe": (
        "Run a 12-well calibrated pilot first: 3 media-only blanks, 3 promoters spanning the dynamic range "
        "at 3 biological replicates each, scattered across interior wells. Subtract the blank mean, divide "
        "by OD600, drop any part below blank+3SD, and only scale to the full 96-well library if every "
        "remaining promoter reports under 15% CV."
    ),
    "tags": ["igem", "gfp", "promoter-screen", "plate-reader", "normalization", "negative-result", "synthetic-fixture"],
}


class SyntheticPlateFixtureTest(unittest.TestCase):
    """The generated data must actually exhibit the failure it claims."""

    def test_uncalibrated_raw_readings_reproduce_the_recorded_38_percent_cv(self) -> None:
        wells = uncalibrated_screen()
        self.assertEqual(len(wells), 96)
        blank_mean = statistics.mean(float(well["_autofluorescence"]) for well in wells)
        limit = detection_limit([float(well["_autofluorescence"]) for well in wells])

        raw = grouped_raw(wells)
        rankable = [name for name, values in raw.items() if statistics.mean(values) > limit]
        raw_cv = statistics.mean(cv_percent(raw[name]) for name in rankable)
        normalised = normalised_units([w for w in wells if w["promoter"] in rankable], blank_mean)
        normalised_cv = statistics.mean(cv_percent(values) for values in normalised.values())

        self.assertAlmostEqual(raw_cv, 38.0, delta=1.0)
        self.assertLess(normalised_cv, CV_GATE_PERCENT)

    def test_raw_fluorescence_ranks_the_wrong_promoter_first(self) -> None:
        """The concrete harm: the screen would have crowned the wrong winner."""
        wells = uncalibrated_screen()
        blank_mean = statistics.mean(float(well["_autofluorescence"]) for well in wells)
        limit = detection_limit([float(well["_autofluorescence"]) for well in wells])

        raw = grouped_raw(wells)
        rankable = [name for name, values in raw.items() if statistics.mean(values) > limit]
        truth = sorted(rankable, key=lambda name: -PROMOTER_STRENGTH[name])

        by_raw = sorted(rankable, key=lambda name: -statistics.mean(raw[name]))
        normalised = normalised_units([w for w in wells if w["promoter"] in rankable], blank_mean)
        by_normalised = sorted(rankable, key=lambda name: -statistics.mean(normalised[name]))

        self.assertEqual(truth[0], "J23100")
        self.assertEqual(by_raw[0], "J23101", "raw readings should crown the wrong promoter")
        self.assertNotEqual(by_raw, truth)
        self.assertEqual(by_normalised, truth, "blank-subtracted GFP/OD600 should recover the true order")

    def test_dark_promoter_is_reported_as_below_detection_not_as_weak(self) -> None:
        wells = uncalibrated_screen()
        limit = detection_limit([float(well["_autofluorescence"]) for well in wells])
        raw = grouped_raw(wells)
        below = [name for name, values in raw.items() if statistics.mean(values) <= limit]
        self.assertEqual(below, ["J23113"], "only the near-dead Anderson part sits under blank+3SD")

    def test_calibrated_pilot_passes_the_15_percent_go_no_go_gate(self) -> None:
        pilot = calibrated_pilot()
        blanks = [float(well["raw_fluorescence"]) for well in pilot["blanks"]]
        self.assertEqual(len(blanks), 3)
        self.assertEqual(len(pilot["samples"]), 9)

        normalised = normalised_units(pilot["samples"], statistics.mean(blanks))
        per_promoter = {name: cv_percent(values) for name, values in normalised.items()}
        self.assertEqual(len(per_promoter), 3)
        for name, value in per_promoter.items():
            self.assertLess(value, CV_GATE_PERCENT, f"{name} pilot CV {value:.1f}% should clear the gate")


class ScreenExperienceCaptureTest(unittest.TestCase):
    """The failed screen must survive capture, verification, and teammate reuse."""

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.store = ExperienceStore(Path(self.temporary_directory.name) / "igem.sqlite3")

    def tearDown(self) -> None:
        self.store.close()
        self.temporary_directory.cleanup()

    def _record_screen(self, *, visibility: str = "team") -> dict[str, object]:
        wells = uncalibrated_screen()
        limit = detection_limit([float(well["_autofluorescence"]) for well in wells])
        raw = grouped_raw(wells)
        rankable = [name for name, values in raw.items() if statistics.mean(values) > limit]
        measured_cv = round(statistics.mean(cv_percent(raw[name]) for name in rankable), 1)

        candidate = self.store.create_candidate({
            "actor": {"id": "tom@org.system", "display_name": "Tom"},
            "task": SCREEN_LESSON["task"],
            "trace_summary": SCREEN_LESSON["trace_summary"],
            "tool_name": "Plate reader export via org.system capture",
            "tags": SCREEN_LESSON["tags"],
            "rationale": SCREEN_LESSON["reuse_recipe"],
            "visibility": visibility,
            "consent": True,
            "outcome": "failure",
            "domain_extension": {
                "domain": "wet-lab/synthetic-biology",
                "reuse_recipe": SCREEN_LESSON["reuse_recipe"],
                "resource_evidence": {
                    "wet_lab_days": 6.0,
                    "wells_consumed": 96,
                    "raw_cv_pct": measured_cv,
                    "cv_gate_pct": CV_GATE_PERCENT,
                },
                "data_provenance": "SYNTHETIC — simulated plate readings, not measurements",
            },
        })
        return self.store.verify(candidate["id"], verify(candidate, {
            "method": "outcome_signal", "evidence_confirmed": True,
        }))

    def test_failed_screen_is_verified_as_a_reusable_negative_result(self) -> None:
        saved = self._record_screen()
        self.assertEqual(saved["status"], "verified")
        self.assertEqual(saved["outcome"]["status"], "failure", "a failed screen must not be stored as a success")
        self.assertEqual(saved["verification"]["verdict"], "VERIFIED")
        self.assertTrue(saved["content"]["what_failed"], "the failure narrative is the reusable payload")
        self.assertEqual(saved["domain_extension"]["resource_evidence"]["raw_cv_pct"], 38.0)
        self.assertTrue(str(self.store.hash_for(saved["id"])).startswith("sha256:"))

    def test_teammate_proposing_the_same_screen_is_intercepted_with_attribution(self) -> None:
        saved = self._record_screen()
        called = handle(1, "tools/call", {
            "name": "avoid_duplicate_work",
            "arguments": {
                "proposal": "Screen the full 96-well GFP promoter library and compare raw fluorescence to rank promoter strength",
                "consumer": "mei@org.system",
            },
        }, self.store)
        payload = json.loads(called["result"]["content"][0]["text"])

        self.assertTrue(payload["matched"])
        receipt = payload["verified_receipts"][0]
        self.assertEqual(receipt["experience_id"], saved["id"])
        self.assertEqual(receipt["actor"], "Tom", "attribution must survive retrieval")
        self.assertEqual(receipt["verification"]["last_verdict"], "VERIFIED")
        self.assertIn("12-well calibrated pilot", receipt["reuse_recipe"])
        self.assertEqual(receipt["resource_evidence"]["wet_lab_days"], 6.0)

    def test_reuse_is_counted_against_the_originating_receipt(self) -> None:
        saved = self._record_screen()
        self.store.recall(query=SCREEN_LESSON["task"], consumer="mei@org.system", limit=3, record_usage=True)
        refreshed = self.store.get(saved["id"])
        self.assertEqual(refreshed["usage"]["times_served"], 1)
        self.assertIn("mei@org.system", refreshed["usage"]["served_to"])

    def test_private_screen_stays_invisible_to_teammates(self) -> None:
        saved = self._record_screen(visibility="private")
        teammate = self.store.recall(query=SCREEN_LESSON["task"], consumer="mei@org.system", limit=3, record_usage=False)
        owner = self.store.recall(query=SCREEN_LESSON["task"], consumer="tom@org.system", limit=3, record_usage=False)
        self.assertFalse(any(hit["experience_id"] == saved["id"] for hit in teammate))
        self.assertTrue(any(hit["experience_id"] == saved["id"] for hit in owner))

    def test_reused_screen_counts_six_wet_lab_days_as_avoided_cost(self) -> None:
        """Bench time is accounted like GPU time: reusing the receipt avoids six days."""
        self._record_screen()
        self.store.recall(query=SCREEN_LESSON["task"], consumer="mei@org.system", limit=3, record_usage=True)
        impact = self.store.impact_dashboard()
        self.assertEqual(impact["reuse_events"], 1)
        self.assertEqual(impact["wet_lab_days_avoided"], 6.0)
        self.assertEqual(impact["duplicate_jobs_intercepted"], 1)
        self.assertEqual(impact["gpu_hours_avoided"], 0.0, "a wet-lab screen must not invent GPU savings")

    def test_lineage_reports_the_avoided_cost_in_wet_lab_units(self) -> None:
        self._record_screen()
        self.store.recall(query=SCREEN_LESSON["task"], consumer="mei@org.system", limit=3, record_usage=True)
        links = self.store.team_dashboard()["inheritance_links"]
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["source"], "Tom")
        self.assertEqual(links[0]["value"], "6 wet-lab days avoided")

    def test_mcp_record_completed_work_preserves_a_reported_failure(self) -> None:
        """The screen recorded through the MCP tool must stay a failure, not become a win."""
        called = handle(1, "tools/call", {
            "name": "record_completed_work",
            "arguments": {
                "actor": "Tom", "task": SCREEN_LESSON["task"],
                "trace_summary": SCREEN_LESSON["trace_summary"],
                "what_worked": SCREEN_LESSON["reuse_recipe"],
                "tags": SCREEN_LESSON["tags"],
                "outcome": "failure", "evidence_confirmed": True,
            },
        }, self.store)
        payload = json.loads(called["result"]["content"][0]["text"])
        self.assertEqual(payload["status"], "verified")

        stored = self.store.get(payload["experience_id"])
        self.assertEqual(stored["outcome"]["status"], "failure")
        self.assertTrue(stored["content"]["what_failed"])

    def test_mcp_record_completed_work_rejects_an_unknown_outcome(self) -> None:
        called = handle(1, "tools/call", {
            "name": "record_completed_work",
            "arguments": {
                "actor": "Tom", "task": SCREEN_LESSON["task"], "trace_summary": "x",
                "what_worked": "y", "outcome": "catastrophe", "evidence_confirmed": True,
            },
        }, self.store)
        self.assertIn("error", called)
        self.assertIn("outcome must be one of", called["error"]["message"])

    def test_mcp_record_completed_work_still_defaults_to_success(self) -> None:
        called = handle(1, "tools/call", {
            "name": "record_completed_work",
            "arguments": {
                "actor": "Mei", "task": "Reduce CI image build time",
                "trace_summary": "Layer cache restored and the measured build passed.",
                "what_worked": "Restore the dependency layer before compilation.",
                "evidence_confirmed": True,
            },
        }, self.store)
        payload = json.loads(called["result"]["content"][0]["text"])
        self.assertEqual(self.store.get(payload["experience_id"])["outcome"]["status"], "success")

    def test_mcp_captured_failure_with_evidence_is_credited_on_reuse(self) -> None:
        """The capture gap is closed: wet-lab days passed through the MCP tool are scored.

        Before the fix the tool had no resource_evidence parameter, so a screen recorded
        over MCP stored resource_evidence={} and the impact dashboard credited nothing.
        """
        called = handle(1, "tools/call", {
            "name": "record_completed_work",
            "arguments": {
                "actor": "Tom", "task": SCREEN_LESSON["task"],
                "trace_summary": SCREEN_LESSON["trace_summary"],
                "what_worked": SCREEN_LESSON["reuse_recipe"],
                "tags": SCREEN_LESSON["tags"], "outcome": "failure", "evidence_confirmed": True,
                "resource_evidence": {"wet_lab_days": 6, "wells_consumed": 96},
            },
        }, self.store)
        payload = json.loads(called["result"]["content"][0]["text"])
        stored = self.store.get(payload["experience_id"])
        self.assertEqual(stored["domain_extension"]["resource_evidence"]["wet_lab_days"], 6.0)
        self.assertEqual(stored["domain_extension"]["resource_evidence"]["wells_consumed"], 96.0)

        self.store.recall(query=SCREEN_LESSON["task"], consumer="mei@org.system", limit=3, record_usage=True)
        impact = self.store.impact_dashboard()
        self.assertEqual(impact["wet_lab_days_avoided"], 6.0, "recognized key is credited")
        self.assertEqual(impact["duplicate_jobs_intercepted"], 1)
        self.assertEqual(impact["gpu_hours_avoided"], 0.0, "an unrelated dimension is not invented")

    def test_mcp_record_completed_work_rejects_non_numeric_evidence(self) -> None:
        called = handle(1, "tools/call", {
            "name": "record_completed_work",
            "arguments": {
                "actor": "Tom", "task": SCREEN_LESSON["task"], "trace_summary": "x", "what_worked": "y",
                "evidence_confirmed": True, "resource_evidence": {"wet_lab_days": "six"},
            },
        }, self.store)
        self.assertIn("error", called)
        self.assertIn("must be a number", called["error"]["message"])


if __name__ == "__main__":
    unittest.main()
