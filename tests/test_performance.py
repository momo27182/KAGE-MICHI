from pathlib import Path
import json
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kage_michi.performance import PerformanceRecorder


class PerformanceRecorderTests(unittest.TestCase):
    def test_records_named_phase_and_writes_json(self) -> None:
        recorder = PerformanceRecorder("test-run", {"case_id": "case-1"})

        with recorder.measure("shadow_generation", building_count=3):
            sum(range(100))

        self.assertEqual(len(recorder.events), 1)
        self.assertEqual(recorder.events[0].phase, "shadow_generation")
        self.assertGreaterEqual(recorder.events[0].elapsed_seconds, 0)

        with tempfile.TemporaryDirectory() as directory:
            path = recorder.write_json(Path(directory) / "result.json")
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["run_id"], "test-run")
        self.assertEqual(payload["metadata"]["case_id"], "case-1")
        self.assertEqual(payload["events"][0]["metadata"]["building_count"], 3)
        self.assertGreaterEqual(payload["elapsed_wall_seconds"], 0)
        self.assertGreaterEqual(payload["sum_event_seconds"], 0)

    def test_records_elapsed_time_when_measured_code_fails(self) -> None:
        recorder = PerformanceRecorder("failing-run")

        with self.assertRaises(RuntimeError):
            with recorder.measure("route_search"):
                raise RuntimeError("expected")

        self.assertEqual(len(recorder.events), 1)


if __name__ == "__main__":
    unittest.main()
