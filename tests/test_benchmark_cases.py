from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kage_michi.benchmark_cases import BenchmarkCase, load_benchmark_cases
from kage_michi.legacy_benchmark import case_is_in_scope


class BenchmarkCaseTests(unittest.TestCase):
    def test_repository_cases_are_valid_and_cover_required_categories(self) -> None:
        cases = load_benchmark_cases(ROOT / "benchmarks" / "cases.json")

        self.assertEqual(len(cases), 5)
        self.assertEqual(len({case.case_id for case in cases}), len(cases))
        self.assertTrue(
            {"daylight_route", "night_route", "no_route", "out_of_scope"}
            <= {case.category for case in cases}
        )

    def test_timezone_is_required(self) -> None:
        value = {
            "id": "invalid-time",
            "description": "invalid",
            "category": "daylight_route",
            "start": {"latitude": 34.2, "longitude": 135.1},
            "destination": {"latitude": 34.3, "longitude": 135.2},
            "departure_jst": "2024-08-01T14:00:00",
            "temperature_c": 32,
            "sun_penalty": 10,
            "expectation": {
                "status": "route",
                "shadow_state": "daylight",
                "required_metrics": [],
            },
        }

        with self.assertRaisesRegex(ValueError, "timezone"):
            BenchmarkCase.from_mapping(value)

    def test_out_of_scope_case_is_rejected_before_graph_lookup(self) -> None:
        cases = {
            case.case_id: case
            for case in load_benchmark_cases(ROOT / "benchmarks" / "cases.json")
        }

        self.assertFalse(
            case_is_in_scope(cases["destination_outside_wakayama_station_scope"])
        )
        self.assertTrue(
            case_is_in_scope(
                cases["wakayama_station_to_tanakaguchi_summer_afternoon"]
            )
        )


if __name__ == "__main__":
    unittest.main()
