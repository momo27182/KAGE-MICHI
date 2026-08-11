"""Lightweight KAGE-MICHI Streamlit entry point using prepared local data."""

from __future__ import annotations

from datetime import datetime, time
import os
from pathlib import Path
from time import perf_counter
from zoneinfo import ZoneInfo

import folium
from pyproj import Transformer
import streamlit as st
from streamlit_folium import st_folium

from kage_michi.infrastructure.ui_runtime import (
    calculate_route_cached,
    calculate_shadows_cached,
    load_dataset_cached,
    search_places_cached,
)
from kage_michi.geocoding import PlaceSearchOutcome
from kage_michi.models import GeoPoint
from kage_michi.routing import RouteNotFoundError
from kage_michi.ui import UiInputs, build_disclosure, recalculation_keys


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "data" / "prepared" / "wakayama-station"
JST = ZoneInfo("Asia/Tokyo")
GEOCODER_DOMAIN = os.getenv(
    "KAGE_MICHI_GEOCODER_DOMAIN", "nominatim.openstreetmap.org"
)
GEOCODER_USER_AGENT = os.getenv(
    "KAGE_MICHI_GEOCODER_USER_AGENT",
    "KAGE-MICHI/0.1 (+https://github.com/momo27182/KAGE-MICHI)",
)


def _show_search_message(outcome: PlaceSearchOutcome) -> None:
    if outcome.status in {"timeout", "unavailable"}:
        st.error(outcome.message)
    elif outcome.status in {"no_results", "out_of_scope", "empty_query"}:
        st.warning(outcome.message)
    elif outcome.status == "ambiguous":
        st.info(outcome.message)
    else:
        st.success(outcome.message)


def _render_place_search(
    role: str,
    label: str,
    data_directory: str,
    latitude_key: str,
    longitude_key: str,
) -> None:
    query_key = f"{role}_place_query"
    outcome_key = f"{role}_place_outcome"
    searched_query_key = f"{role}_searched_query"
    st.text_input(f"{label}の地名・住所・施設名", key=query_key)
    if st.button(f"{label}の候補を検索", key=f"{role}_search_button"):
        try:
            manifest_path = Path(data_directory).resolve() / "manifest.json"
            version = str(manifest_path.stat().st_mtime_ns)
            normalized_query = " ".join(st.session_state[query_key].split())
            st.session_state[outcome_key] = search_places_cached(
                normalized_query,
                str(Path(data_directory).resolve()),
                version,
                GEOCODER_DOMAIN,
                GEOCODER_USER_AGENT,
            )
            st.session_state[searched_query_key] = st.session_state[query_key]
        except (FileNotFoundError, ValueError) as error:
            st.session_state[outcome_key] = PlaceSearchOutcome(
                "unavailable", (), f"検索範囲を読み込めません: {error}"
            )

    outcome = st.session_state.get(outcome_key)
    if not isinstance(outcome, PlaceSearchOutcome):
        return
    if st.session_state.get(searched_query_key) != st.session_state[query_key]:
        st.caption("入力が変わっています。「候補を検索」を押して更新してください。")
    _show_search_message(outcome)
    if not outcome.candidates:
        return
    selected_index = st.selectbox(
        f"{label}の候補",
        range(len(outcome.candidates)),
        format_func=lambda index: outcome.candidates[index].display_label,
        key=f"{role}_candidate_index",
    )
    candidate = outcome.candidates[selected_index]
    if st.button(
        f"選択した候補を{label}へ反映",
        key=f"{role}_apply_candidate",
        disabled=not candidate.in_scope,
    ):
        st.session_state[latitude_key] = candidate.point.latitude
        st.session_state[longitude_key] = candidate.point.longitude
        st.success(f"{label}へ「{candidate.name}」を反映しました。")

st.set_page_config(page_title="KAGE-MICHI", page_icon="🌳", layout="centered")
st.title("KAGE-MICHI")
st.caption("時間帯の日陰を考慮した徒歩経路の試作版")

st.session_state.setdefault("start_latitude", 34.2325)
st.session_state.setdefault("start_longitude", 135.1917)
st.session_state.setdefault("destination_latitude", 34.2241)
st.session_state.setdefault("destination_longitude", 135.1906)

with st.sidebar:
    st.header("経路条件")
    data_directory = st.text_input("加工済みデータ", str(DEFAULT_DATA))
    st.subheader("地名から地点を選択")
    _render_place_search(
        "start", "出発地", data_directory, "start_latitude", "start_longitude"
    )
    _render_place_search(
        "destination",
        "目的地",
        data_directory,
        "destination_latitude",
        "destination_longitude",
    )
    st.caption(
        "検索語はOpenStreetMapのNominatimへ送信されます。自動検索は行わず、"
        "検索ボタン操作時だけ問い合わせ、同一結果を7日間キャッシュします。"
        "個人情報や機密情報は入力しないでください。"
    )
    st.subheader("緯度経度（確認・手動修正）")
    start_latitude = st.number_input(
        "出発地 緯度", format="%.6f", key="start_latitude"
    )
    start_longitude = st.number_input(
        "出発地 経度", format="%.6f", key="start_longitude"
    )
    destination_latitude = st.number_input(
        "目的地 緯度", format="%.6f", key="destination_latitude"
    )
    destination_longitude = st.number_input(
        "目的地 経度", format="%.6f", key="destination_longitude"
    )
    departure_date = st.date_input("出発日", value=datetime.now(JST).date())
    departure_time = st.time_input("出発時刻", value=time(14, 0))
    sun_penalty = st.slider("日向の距離ペナルティ", 1.0, 20.0, 10.0, 1.0)
    calculate = st.button("経路を計算", type="primary", use_container_width=True)

st.info(
    "再計算範囲: 地点・ペナルティ変更は経路のみ、日時変更は影と経路、"
    "加工済みデータ変更は全処理を更新します。"
)

if calculate:
    try:
        request_started = perf_counter()
        dataset_path = Path(data_directory).resolve()
        manifest_path = dataset_path / "manifest.json"
        data_version = str(manifest_path.stat().st_mtime_ns)
        departure = datetime.combine(departure_date, departure_time, JST)
        inputs = UiInputs(
            str(dataset_path),
            GeoPoint(start_latitude, start_longitude),
            GeoPoint(destination_latitude, destination_longitude),
            departure,
            sun_penalty,
        )
        keys = recalculation_keys(inputs, data_version)
        dataset = load_dataset_cached(*keys.dataset)
        shadows = calculate_shadows_cached(
            keys.dataset[0], keys.dataset[1], departure.isoformat()
        )
        route = calculate_route_cached(
            keys.dataset[0],
            keys.dataset[1],
            departure.isoformat(),
            start_latitude,
            start_longitude,
            destination_latitude,
            destination_longitude,
            sun_penalty,
        )
        total_seconds = perf_counter() - request_started
        disclosure = build_disclosure(
            dataset, shadows.result, route.result, departure, route.calculated_at
        )

        first, second, third = st.columns(3)
        first.metric("経路距離", f"{disclosure.route_distance_m:,.0f} m")
        second.metric("推定日陰率", f"{disclosure.shade_ratio_pct:.1f}%")
        third.metric("表示処理", f"{total_seconds:.3f} 秒")
        st.write(f"推定日向距離: {disclosure.sunny_distance_m:,.0f} m")
        graph = dataset.payload.graph
        transformer = Transformer.from_crs(
            graph.graph["crs"], "EPSG:4326", always_xy=True
        )
        route_coordinates = []
        for node_id in route.result.node_ids:
            node = graph.nodes[node_id]
            longitude, latitude = transformer.transform(node["x"], node["y"])
            route_coordinates.append((latitude, longitude))
        route_map = folium.Map(
            location=[start_latitude, start_longitude], zoom_start=15
        )
        folium.PolyLine(route_coordinates, color="#167d4a", weight=7).add_to(
            route_map
        )
        folium.Marker(
            [start_latitude, start_longitude], tooltip="出発地"
        ).add_to(route_map)
        folium.Marker(
            [destination_latitude, destination_longitude], tooltip="目的地"
        ).add_to(route_map)
        st_folium(route_map, height=460, use_container_width=True, returned_objects=[])
        with st.expander("計算根拠・時刻・データ情報", expanded=True):
            st.write(f"対象日時: `{disclosure.departure_iso}`")
            st.write(f"計算実行時刻: `{disclosure.calculated_at_iso}`")
            st.write(f"データ取得処理日時: `{disclosure.data_acquired_at}`")
            st.write(f"データ出典: {disclosure.data_source} / © OpenStreetMap contributors")
            st.write(f"データ範囲: `{disclosure.data_scope}`")
            st.write(
                f"内訳（未キャッシュ計算時）: 影 {shadows.elapsed_seconds:.3f}秒 / "
                f"経路 {route.elapsed_seconds:.3f}秒"
            )
        for warning in disclosure.warnings:
            st.warning(warning)
    except (FileNotFoundError, ValueError, RouteNotFoundError) as error:
        st.error(str(error))
else:
    st.write("サイドバーで条件を確認し、「経路を計算」を押してください。")
