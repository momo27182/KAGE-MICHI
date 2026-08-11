"""Cached runtime functions used by the lightweight Streamlit screen."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

import streamlit as st

from ..data import SpatialDataset
from ..geocoding import PlaceSearchOutcome, SearchArea, search_places
from ..models import GeoPoint, RouteResult
from ..shadows import ShadowResult
from .nominatim_geocoder import NominatimPlaceGeocoder
from .osm_prepared import (
    MANIFEST_FILE,
    PreparedDatasetManifest,
    load_prepared_dataset,
    validate_dataset_scope,
)
from .shade_route_planner import MidpointShadeRoutePlanner
from .shadow_calculator import BuildingShadowCalculator


@dataclass(frozen=True)
class TimedShadows:
    result: ShadowResult
    elapsed_seconds: float
    calculated_at: datetime


@dataclass(frozen=True)
class TimedRoute:
    result: RouteResult
    elapsed_seconds: float
    calculated_at: datetime


@st.cache_resource
def get_place_geocoder(
    domain: str, user_agent: str, timeout_seconds: float
) -> NominatimPlaceGeocoder:
    return NominatimPlaceGeocoder(
        domain=domain,
        user_agent=user_agent,
        timeout_seconds=timeout_seconds,
    )


@st.cache_data(ttl=7 * 24 * 60 * 60, max_entries=256, show_spinner="地名を検索しています…")
def search_places_cached(
    query: str,
    data_directory: str,
    data_version: str,
    domain: str,
    user_agent: str,
    timeout_seconds: float = 5.0,
) -> PlaceSearchOutcome:
    del data_version
    manifest = PreparedDatasetManifest.from_json(
        Path(data_directory) / MANIFEST_FILE
    )
    area = SearchArea(GeoPoint(**manifest.center), manifest.radius_m)
    geocoder = get_place_geocoder(domain, user_agent, timeout_seconds)
    return search_places(query, geocoder, area)


@st.cache_resource(show_spinner="加工済み地図データを読み込んでいます…")
def load_dataset_cached(data_directory: str, data_version: str) -> SpatialDataset:
    del data_version
    return load_prepared_dataset(Path(data_directory))


@st.cache_data(show_spinner="指定時刻の影を計算しています…")
def calculate_shadows_cached(
    data_directory: str,
    data_version: str,
    departure_iso: str,
) -> TimedShadows:
    dataset = load_dataset_cached(data_directory, data_version)
    manifest = dataset.payload.manifest
    center = GeoPoint(**manifest.center)
    started = perf_counter()
    result = BuildingShadowCalculator(center=center).calculate(
        dataset, datetime.fromisoformat(departure_iso)
    )
    return TimedShadows(result, perf_counter() - started, datetime.now(timezone.utc))


@st.cache_data(show_spinner="日陰を考慮した経路を探索しています…")
def calculate_route_cached(
    data_directory: str,
    data_version: str,
    departure_iso: str,
    start_latitude: float,
    start_longitude: float,
    destination_latitude: float,
    destination_longitude: float,
    sun_penalty: float,
) -> TimedRoute:
    dataset = load_dataset_cached(data_directory, data_version)
    start = GeoPoint(start_latitude, start_longitude)
    destination = GeoPoint(destination_latitude, destination_longitude)
    validate_dataset_scope(dataset, start, destination)
    shadows = calculate_shadows_cached(data_directory, data_version, departure_iso)
    started = perf_counter()
    result = MidpointShadeRoutePlanner(sun_penalty).find_route(
        dataset, start, destination, shadows.result
    )
    return TimedRoute(result, perf_counter() - started, datetime.now(timezone.utc))
