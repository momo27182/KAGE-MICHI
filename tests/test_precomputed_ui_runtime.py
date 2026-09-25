from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kage_michi.infrastructure.ui_runtime import load_precomputed_shade_cached


class PrecomputedUiRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        load_precomputed_shade_cached.clear()
        self.addCleanup(load_precomputed_shade_cached.clear)

    def test_same_daily_artifact_is_loaded_once_for_two_times(self) -> None:
        prepared = object()
        with patch(
            "kage_michi.infrastructure.ui_runtime.load_shade_artifact",
            return_value=prepared,
        ) as load:
            first = load_precomputed_shade_cached("shade/day", "v1", "roads")
            second = load_precomputed_shade_cached("shade/day", "v1", "roads")

        self.assertIs(first, second)
        self.assertIs(first.result, prepared)
        load.assert_called_once_with(
            "shade/day", expected_source_sha256={"osm_graph": "roads"}
        )


if __name__ == "__main__":
    unittest.main()
