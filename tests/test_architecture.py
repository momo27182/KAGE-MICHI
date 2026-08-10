import ast
from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "kage_michi"
sys.path.insert(0, str(ROOT / "src"))


PRODUCT_MODULES = {
    "models",
    "data",
    "shadows",
    "routing",
    "heat",
    "application",
    "presentation",
}


def product_dependencies(module: str) -> set[str]:
    tree = ast.parse((PACKAGE / f"{module}.py").read_text(encoding="utf-8"))
    dependencies: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module:
            dependency = node.module.split(".", maxsplit=1)[0]
            if dependency in PRODUCT_MODULES:
                dependencies.add(dependency)
    return dependencies


class ArchitectureTests(unittest.TestCase):
    def test_product_modules_import_without_optional_dependencies(self) -> None:
        for module in PRODUCT_MODULES:
            with self.subTest(module=module):
                import_module(f"kage_michi.{module}")

    def test_product_dependency_graph_has_no_cycles(self) -> None:
        graph = {module: product_dependencies(module) for module in PRODUCT_MODULES}
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(module: str) -> None:
            if module in visiting:
                self.fail(f"circular product dependency detected at {module}")
            if module in visited:
                return
            visiting.add(module)
            for dependency in graph[module]:
                visit(dependency)
            visiting.remove(module)
            visited.add(module)

        for module in graph:
            visit(module)

    def test_application_orchestrates_replaceable_boundaries(self) -> None:
        from kage_michi.application import PlanJourney
        from kage_michi.data import SpatialDataset
        from kage_michi.models import GeoPoint, HeatAssessment, RouteRequest, RouteResult
        from kage_michi.shadows import ShadowResult

        calls: list[str] = []

        class DataSource:
            def load(self, start: GeoPoint, destination: GeoPoint) -> SpatialDataset:
                calls.append("data")
                return SpatialDataset(object(), "test", "2026-08-10", "test", "EPSG:6676")

        class Shadows:
            def calculate(self, dataset: SpatialDataset, departure: datetime) -> ShadowResult:
                calls.append("shadows")
                return ShadowResult(None, 45.0, 180.0)

        class Router:
            def find_route(self, dataset, start, destination, shadows) -> RouteResult:
                calls.append("routing")
                return RouteResult((1, 2), 100.0, 25.0)

        class Heat:
            def evaluate(self, request: RouteRequest, route: RouteResult) -> HeatAssessment:
                calls.append("heat")
                return HeatAssessment("test", "test assessment")

        service = PlanJourney(DataSource(), Shadows(), Router(), Heat())
        result = service.execute(
            RouteRequest(
                GeoPoint(34.2325, 135.1917),
                GeoPoint(34.2241, 135.1906),
                datetime(2024, 8, 1, 14, tzinfo=timezone.utc),
                32.0,
            )
        )

        self.assertEqual(calls, ["data", "shadows", "routing", "heat"])
        self.assertEqual(result.route.shade_ratio_pct, 75.0)
        self.assertEqual(result.heat.level, "test")


if __name__ == "__main__":
    unittest.main()
