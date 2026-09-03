"""Measure server reruns only; NOT browser click-to-paint latency.

Run from repository root: .venv/Scripts/python.exe tests/measure_map_rerun.py
Requires the locally prepared Wakayama manifest. Does not fetch OSM or geocode.
"""

import json
from pathlib import Path
from statistics import median
import sys
from time import perf_counter
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kage_michi.models import GeoPoint


def main():
    if not (ROOT / "data/prepared/wakayama-station/manifest.json").exists():
        raise SystemExit("Prepare the Wakayama dataset first.")
    with patch("kage_michi.infrastructure.ui_runtime.load_dataset_cached") as load, \
         patch("kage_michi.infrastructure.ui_runtime.calculate_shadows_cached") as shadows, \
         patch("kage_michi.infrastructure.ui_runtime.calculate_route_cached") as route:
        app = AppTest.from_file(str(ROOT / "src/streamlit_app.py")).run(timeout=30)
        samples = []
        for index in range(5):
            app.session_state["map_pending"] = GeoPoint(34.23 + index * 0.0001, 135.19)
            started = perf_counter()
            app.run(timeout=30)
            samples.append(perf_counter() - started)
            assert not app.exception
            assert not app.button(key="map_confirm").disabled
        load.assert_not_called()
        shadows.assert_not_called()
        route.assert_not_called()
    print(json.dumps({"measurement": "AppTest server rerun, excludes browser",
                      "seconds": samples, "median_seconds": median(samples),
                      "heavy_function_calls": 0}, indent=2))


if __name__ == "__main__":
    main()
