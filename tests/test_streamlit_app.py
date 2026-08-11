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
        self.assertIn("出発地の候補を検索", [button.label for button in app.button])
        self.assertIn("目的地の候補を検索", [button.label for button in app.button])
        self.assertIn("経路を計算", [button.label for button in app.button])
        self.assertIn("再計算範囲", app.info[0].value)
        self.assertTrue(any("Nominatim" in item.value for item in app.caption))

    def test_search_failure_does_not_start_route_calculation(self) -> None:
        app = AppTest.from_file(str(ROOT / "src" / "streamlit_app.py"))
        app.run(timeout=20)
        app.text_input[0].set_value(str(ROOT / "missing-prepared-data"))
        next(
            button
            for button in app.button
            if button.label == "出発地の候補を検索"
        ).click()

        app.run(timeout=20)

        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any("検索範囲を読み込めません" in item.value for item in app.error))
        self.assertFalse(any("経路距離" in item.label for item in app.metric))


if __name__ == "__main__":
    unittest.main()
