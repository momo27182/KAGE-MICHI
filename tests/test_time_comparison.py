from datetime import datetime
from pathlib import Path
import sys
import tempfile
import unittest
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kage_michi.time_comparison import (
    default_comparison_datetime,
    resolve_shade_artifact,
    validate_comparison_datetimes,
)


JST = ZoneInfo("Asia/Tokyo")


class TimeComparisonTests(unittest.TestCase):
    def test_default_comparison_rolls_into_next_date(self) -> None:
        result = default_comparison_datetime(
            datetime(2026, 8, 11, 23, 30, tzinfo=JST)
        )

        self.assertEqual(result.isoformat(), "2026-08-12T00:30:00+09:00")

    def test_same_datetime_is_rejected(self) -> None:
        value = datetime(2026, 8, 11, 14, 0, tzinfo=JST)

        with self.assertRaisesRegex(ValueError, "異なる日時"):
            validate_comparison_datetimes(value, value)

    def test_timezone_is_required(self) -> None:
        with self.assertRaisesRegex(ValueError, "timezone"):
            default_comparison_datetime(datetime(2026, 8, 11, 14, 0))

    def test_artifact_resolution_uses_requested_calendar_date(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "2026-08-12"
            artifact.mkdir()
            (artifact / "manifest.json").write_text("{}", encoding="utf-8")

            result = resolve_shade_artifact(
                directory, datetime(2026, 8, 12, 0, 30, tzinfo=JST)
            )

            self.assertEqual(result.directory, artifact.resolve())
            self.assertTrue(result.version.isdigit())

    def test_missing_artifact_names_datetime_and_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            requested = datetime(2026, 8, 12, 0, 30, tzinfo=JST)

            with self.assertRaisesRegex(
                FileNotFoundError, "2026-08-12T00:30:00\\+09:00"
            ):
                resolve_shade_artifact(directory, requested)


if __name__ == "__main__":
    unittest.main()
