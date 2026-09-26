from pathlib import Path
import json
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kage_michi.field_validation import (
    FieldObservation,
    read_observations,
    summarize_observations,
    write_observation_template,
    write_validation_report,
)


class FieldValidationTests(unittest.TestCase):
    def observation(self, **overrides) -> FieldObservation:
        values = {
            "observation_id": "wakayama-001",
            "location_name": "和歌山駅西口",
            "latitude": 34.2325,
            "longitude": 135.1917,
            "observed_at": "2026-08-11T14:00:00+09:00",
            "predicted_shade_pct": 40.0,
            "observed_shade_pct": 25.0,
            "weather": "sunny",
            "shade_source": "building",
        }
        values.update(overrides)
        return FieldObservation(**values)

    def test_validates_timezone_percentages_and_categories(self) -> None:
        with self.assertRaisesRegex(ValueError, "timezone"):
            self.observation(observed_at="2026-08-11T14:00:00")
        with self.assertRaisesRegex(ValueError, "between 0 and 100"):
            self.observation(observed_shade_pct=101)
        with self.assertRaisesRegex(ValueError, "weather"):
            self.observation(weather="rainy")

    def test_template_round_trip_and_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            csv_path = write_observation_template(Path(directory) / "observations.csv")
            observations = read_observations(csv_path)
            report = summarize_observations(observations)
            report_path = write_validation_report(report, Path(directory) / "report.json")
            stored = json.loads(report_path.read_text("utf-8"))

        self.assertEqual(len(observations), 1)
        self.assertEqual(stored["schema_version"], 1)
        self.assertEqual(stored["mean_absolute_error_percentage_points"], 5.0)

    def test_summary_reports_signed_and_grouped_error(self) -> None:
        report = summarize_observations([
            self.observation(),
            self.observation(
                observation_id="wakayama-002",
                predicted_shade_pct=20,
                observed_shade_pct=30,
                shade_source="tree",
            ),
        ])
        self.assertEqual(report["mean_error_percentage_points"], 2.5)
        self.assertEqual(report["mean_absolute_error_percentage_points"], 12.5)
        self.assertEqual(report["within_10_percentage_points_count"], 1)
        self.assertEqual(report["by_shade_source"]["tree"]["count"], 1)

    def test_duplicate_ids_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = write_observation_template(Path(directory) / "observations.csv")
            lines = path.read_text("utf-8-sig").splitlines()
            path.write_text("\n".join([lines[0], lines[1], lines[1]]) + "\n", encoding="utf-8-sig")
            with self.assertRaisesRegex(ValueError, "unique"):
                read_observations(path)


if __name__ == "__main__":
    unittest.main()
