"""UI-neutral state and disclosure models for the lightweight app."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .data import SpatialDataset
from .models import GeoPoint, RouteResult
from .shadows import ShadowResult


@dataclass(frozen=True)
class UiInputs:
    data_directory: str
    start: GeoPoint
    destination: GeoPoint
    departure: datetime
    sun_penalty: float


@dataclass(frozen=True)
class RecalculationKeys:
    dataset: tuple[str, str]
    shadows: tuple[tuple[str, str], str]
    route: tuple[tuple[tuple[str, str], str], GeoPoint, GeoPoint, float]


@dataclass(frozen=True)
class ResultDisclosure:
    route_distance_m: float
    sunny_distance_m: float
    shade_ratio_pct: float
    departure_iso: str
    calculated_at_iso: str
    data_acquired_at: str
    data_source: str
    data_scope: str
    warnings: tuple[str, ...]


def recalculation_keys(inputs: UiInputs, data_version: str) -> RecalculationKeys:
    dataset_key = (inputs.data_directory, data_version)
    shadow_key = (dataset_key, inputs.departure.isoformat())
    return RecalculationKeys(
        dataset=dataset_key,
        shadows=shadow_key,
        route=(shadow_key, inputs.start, inputs.destination, inputs.sun_penalty),
    )


def changed_stages(
    previous: RecalculationKeys, current: RecalculationKeys
) -> tuple[str, ...]:
    if previous.dataset != current.dataset:
        return ("dataset", "shadows", "route")
    if previous.shadows != current.shadows:
        return ("shadows", "route")
    if previous.route != current.route:
        return ("route",)
    return ()


def build_disclosure(
    dataset: SpatialDataset,
    shadows: ShadowResult,
    route: RouteResult,
    departure: datetime,
    calculated_at: datetime,
) -> ResultDisclosure:
    warnings = (
        "日陰と経路は推定値であり、暑熱環境や安全を保証するものではありません。",
        "建物高さの欠損は10mで補完しています。PLATEAUは未導入です。",
        "影は建物外形の凸包による簡易モデルです。",
        "道路の日陰は区間中央点だけで判定しています。",
    )
    return ResultDisclosure(
        route_distance_m=route.distance_m,
        sunny_distance_m=route.sunny_distance_m,
        shade_ratio_pct=route.shade_ratio_pct,
        departure_iso=departure.isoformat(),
        calculated_at_iso=calculated_at.isoformat(),
        data_acquired_at=dataset.acquired_at,
        data_source=dataset.source,
        data_scope=dataset.scope,
        warnings=warnings,
    )
