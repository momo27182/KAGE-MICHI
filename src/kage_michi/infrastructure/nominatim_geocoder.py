"""Nominatim adapter used only for explicit end-user place searches."""

from __future__ import annotations

from collections.abc import Callable
import math
from typing import Any

from geopy.exc import (
    GeocoderQuotaExceeded,
    GeocoderServiceError,
    GeocoderTimedOut,
    GeocoderUnavailable,
)
from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import Nominatim

from ..geocoding import (
    GeocodingResult,
    PlaceSearchTimedOut,
    PlaceSearchUnavailable,
    SearchArea,
)
from ..models import GeoPoint


WAKAYAMA_QUERY_ALIASES = {
    "和歌山駅": "Wakayama Station, Wakayama, Japan",
    "田中口駅": "Tanakaguchi Station, Wakayama, Japan",
    "紀和駅": "Kiwa Station, Wakayama, Japan",
}


class NominatimPlaceGeocoder:
    def __init__(
        self,
        *,
        user_agent: str,
        domain: str = "nominatim.openstreetmap.org",
        timeout_seconds: float = 5.0,
        geocode_function: Callable[..., Any] | None = None,
        query_aliases: dict[str, str] | None = None,
    ) -> None:
        if not user_agent.strip():
            raise ValueError("a distinct Nominatim user_agent is required")
        if geocode_function is None:
            locator = Nominatim(
                user_agent=user_agent,
                domain=domain,
                timeout=timeout_seconds,
            )
            geocode_function = locator.geocode
        self._geocode = RateLimiter(
            geocode_function,
            min_delay_seconds=1.0,
            max_retries=0,
            swallow_exceptions=False,
        )
        self._query_aliases = (
            WAKAYAMA_QUERY_ALIASES if query_aliases is None else query_aliases
        )

    def geocode(self, query: str, area: SearchArea) -> tuple[GeocodingResult, ...]:
        latitude_delta = area.radius_m / 111_320
        longitude_scale = max(0.1, abs(math.cos(math.radians(area.center.latitude))))
        longitude_delta = area.radius_m / (111_320 * longitude_scale)
        viewbox = [
            (
                area.center.latitude - latitude_delta,
                area.center.longitude - longitude_delta,
            ),
            (
                area.center.latitude + latitude_delta,
                area.center.longitude + longitude_delta,
            ),
        ]
        provider_query = self._query_aliases.get(query, f"{query}, 和歌山県, 日本")
        try:
            locations = self._geocode(
                provider_query,
                exactly_one=False,
                limit=10,
                country_codes="jp",
                viewbox=viewbox,
                bounded=False,
                addressdetails=True,
                namedetails=True,
                language="ja",
            )
        except GeocoderTimedOut as error:
            raise PlaceSearchTimedOut from error
        except (
            GeocoderQuotaExceeded,
            GeocoderServiceError,
            GeocoderUnavailable,
        ) as error:
            raise PlaceSearchUnavailable from error

        converted = []
        for location in locations or ():
            raw = location.raw
            namedetails = raw.get("namedetails") or {}
            if query in self._query_aliases and raw.get("type") in {"station", "halt"}:
                name = query
            else:
                name = (
                    namedetails.get("name:ja")
                    or namedetails.get("name")
                    or raw.get("name")
                    or location.address.split(",", 1)[0]
                )
            provider_type = raw.get("osm_type", "place")
            provider_number = raw.get("osm_id", raw.get("place_id", "unknown"))
            provider_id = f"{provider_type}:{provider_number}"
            converted.append(
                GeocodingResult(
                    str(name),
                    location.address,
                    GeoPoint(float(location.latitude), float(location.longitude)),
                    provider_id,
                )
            )
        return tuple(converted)
