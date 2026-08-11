"""UI-neutral place-search models and stable candidate selection."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Protocol

from .models import GeoPoint


@dataclass(frozen=True)
class SearchArea:
    center: GeoPoint
    radius_m: float

    def __post_init__(self) -> None:
        if self.radius_m <= 0:
            raise ValueError("radius_m must be positive")


@dataclass(frozen=True)
class GeocodingResult:
    name: str
    address: str
    point: GeoPoint
    provider_id: str


class PlaceGeocoder(Protocol):
    def geocode(self, query: str, area: SearchArea) -> tuple[GeocodingResult, ...]:
        """Return provider results without applying product-specific ranking."""


class PlaceSearchError(RuntimeError):
    """Base class for user-visible geocoding failures."""


class PlaceSearchTimedOut(PlaceSearchError):
    """The provider did not answer within the configured timeout."""


class PlaceSearchUnavailable(PlaceSearchError):
    """The provider rejected the request or is temporarily unavailable."""


@dataclass(frozen=True)
class PlaceCandidate:
    name: str
    address: str
    point: GeoPoint
    distance_from_center_m: float
    in_scope: bool
    provider_id: str

    @property
    def display_label(self) -> str:
        scope = "範囲内" if self.in_scope else "対象範囲外"
        return (
            f"{self.name} — {self.address} "
            f"（中心から{self.distance_from_center_m:,.0f}m・{scope}）"
        )


@dataclass(frozen=True)
class PlaceSearchOutcome:
    status: str
    candidates: tuple[PlaceCandidate, ...]
    message: str


def search_places(
    query: str,
    geocoder: PlaceGeocoder,
    area: SearchArea,
    *,
    limit: int = 10,
) -> PlaceSearchOutcome:
    normalized = " ".join(query.split())
    if not normalized:
        return PlaceSearchOutcome("empty_query", (), "地名、住所、施設名を入力してください。")

    try:
        results = geocoder.geocode(normalized, area)
    except PlaceSearchTimedOut:
        return PlaceSearchOutcome(
            "timeout", (), "地名検索がタイムアウトしました。少し待って再試行してください。"
        )
    except PlaceSearchUnavailable:
        return PlaceSearchOutcome(
            "unavailable",
            (),
            "地名検索サービスを利用できません。緯度経度入力は引き続き利用できます。",
        )

    candidates = _rank_and_deduplicate(results, area)[:limit]
    if not candidates:
        return PlaceSearchOutcome(
            "no_results", (), "一致する候補がありません。住所や施設名を詳しくしてください。"
        )
    in_scope_count = sum(candidate.in_scope for candidate in candidates)
    if in_scope_count == 0:
        return PlaceSearchOutcome(
            "out_of_scope",
            candidates,
            "候補は見つかりましたが、すべて加工済みデータの対象範囲外です。",
        )
    if in_scope_count > 1:
        return PlaceSearchOutcome(
            "ambiguous",
            candidates,
            "範囲内に複数候補があります。名称、住所、距離を確認して選択してください。",
        )
    return PlaceSearchOutcome("results", candidates, "範囲内の候補が見つかりました。")


def _rank_and_deduplicate(
    results: tuple[GeocodingResult, ...], area: SearchArea
) -> tuple[PlaceCandidate, ...]:
    unique: dict[tuple[str, int, int], PlaceCandidate] = {}
    for result in results:
        distance = distance_m(area.center, result.point)
        candidate = PlaceCandidate(
            name=result.name.strip() or result.address.split(",", 1)[0].strip(),
            address=result.address.strip(),
            point=result.point,
            distance_from_center_m=distance,
            in_scope=distance <= area.radius_m,
            provider_id=result.provider_id,
        )
        key = (
            candidate.name.casefold(),
            round(candidate.point.latitude * 100_000),
            round(candidate.point.longitude * 100_000),
        )
        current = unique.get(key)
        if current is None or len(candidate.address) > len(current.address):
            unique[key] = candidate
    return tuple(
        sorted(
            unique.values(),
            key=lambda item: (
                not item.in_scope,
                item.distance_from_center_m,
                item.name.casefold(),
                item.provider_id,
            ),
        )
    )


def distance_m(a: GeoPoint, b: GeoPoint) -> float:
    radius = 6_371_008.8
    lat1, lat2 = math.radians(a.latitude), math.radians(b.latitude)
    delta_lat = lat2 - lat1
    delta_lon = math.radians(b.longitude - a.longitude)
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(haversine))
