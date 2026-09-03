"""Validation of provisional map selections, independent of UI and routing."""

from .geocoding import SearchArea, distance_m
from .models import GeoPoint


def validate_selection(point: GeoPoint, area: SearchArea, other: GeoPoint) -> None:
    if distance_m(point, area.center) > area.radius_m:
        raise ValueError("対象範囲外です。円の内側を選択してください。")
    if distance_m(point, other) < 1.0:
        raise ValueError("出発地と目的地が同一点です。1m以上離して選択してください。")
