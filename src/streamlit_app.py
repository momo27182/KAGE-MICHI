"""Lightweight KAGE-MICHI Streamlit entry point using prepared local data."""

from __future__ import annotations

from datetime import datetime, time
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
)
from kage_michi.models import GeoPoint
from kage_michi.routing import RouteNotFoundError
from kage_michi.ui import UiInputs, build_disclosure, recalculation_keys


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "data" / "prepared" / "wakayama-station"
JST = ZoneInfo("Asia/Tokyo")

st.set_page_config(page_title="KAGE-MICHI", page_icon="🌳", layout="centered")
st.title("KAGE-MICHI")
st.caption("時間帯の日陰を考慮した徒歩経路の試作版")

with st.sidebar:
    st.header("経路条件")
    data_directory = st.text_input("加工済みデータ", str(DEFAULT_DATA))
    start_latitude = st.number_input("出発地 緯度", value=34.2325, format="%.6f")
    start_longitude = st.number_input("出発地 経度", value=135.1917, format="%.6f")
    destination_latitude = st.number_input("目的地 緯度", value=34.2241, format="%.6f")
    destination_longitude = st.number_input("目的地 経度", value=135.1906, format="%.6f")
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
