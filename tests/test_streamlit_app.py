from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]


class StreamlitAppTests(unittest.TestCase):
    def test_screen_starts_without_loading_external_data(self) -> None:
        app = AppTest.from_file(str(ROOT / "src" / "streamlit_app.py"))

        app.run(timeout=20)

        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.title[0].value, "KAGE-MICHI")
        self.assertEqual(app.button[0].label, "経路を計算")
        self.assertIn("再計算範囲", app.info[0].value)


if __name__ == "__main__":
    unittest.main()
