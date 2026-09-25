"""Lightweight KAGE-MICHI Streamlit entry point using prepared local data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
import os
from pathlib import Path
from time import perf_counter
from zoneinfo import ZoneInfo

from pyproj import Transformer
import streamlit as st
from kage_michi.infrastructure.map_picker import clear_candidate, render_picker
from kage_michi.infrastructure.osm_prepared import PreparedDatasetManifest
from kage_michi.map_selection import validate_selection

from kage_michi.infrastructure.ui_runtime import (
    calculate_route_comparison_cached,
    load_facilities_cached,
    load_dataset_cached,
    search_places_cached,
)
from kage_michi.geocoding import PlaceSearchOutcome, SearchArea
from kage_michi.models import GeoPoint, RouteComparison
from kage_michi.routing import RouteNotFoundError
from kage_michi.time_comparison import (
    default_comparison_datetime,
    resolve_shade_artifact,
    validate_comparison_datetimes,
)
from kage_michi.ui import (
    ResultDisclosure,
    UiInputs,
    build_disclosure,
    recalculation_keys,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "data" / "prepared" / "wakayama-station"
DEFAULT_SHADE_DATA = ROOT / "data" / "prepared" / "shade" / "wakayama-station"
JST = ZoneInfo("Asia/Tokyo")
GEOCODER_DOMAIN = os.getenv(
    "KAGE_MICHI_GEOCODER_DOMAIN", "nominatim.openstreetmap.org"
)
GEOCODER_USER_AGENT = os.getenv(
    "KAGE_MICHI_GEOCODER_USER_AGENT",
    "KAGE-MICHI/0.1 (+https://github.com/momo27182/KAGE-MICHI)",
)


@dataclass(frozen=True)
class RouteTimeView:
    departure: datetime
    disclosure: ResultDisclosure
    shortest_disclosure: ResultDisclosure
    comparison: RouteComparison
    route_coordinates: tuple[tuple[float, float], ...]
    shortest_coordinates: tuple[tuple[float, float], ...]
    shade_timestamp: str
    daylight: bool
    shade_load_seconds: float
    route_seconds: float


def _show_search_message(outcome: PlaceSearchOutcome) -> None:
    if outcome.status in {"timeout", "unavailable"}:
        st.error(outcome.message)
    elif outcome.status in {"no_results", "out_of_scope", "empty_query"}:
        st.warning(outcome.message)
    elif outcome.status == "ambiguous":
        st.info(outcome.message)
    else:
        st.success(outcome.message)


def _route_coordinates(graph, node_ids: tuple[int, ...]) -> tuple[tuple[float, float], ...]:
    transformer = Transformer.from_crs(
        graph.graph["crs"], "EPSG:4326", always_xy=True
    )
    coordinates = []
    for node_id in node_ids:
        node = graph.nodes[node_id]
        longitude, latitude = transformer.transform(node["x"], node["y"])
        coordinates.append((latitude, longitude))
    return tuple(coordinates)


def _calculate_time_view(
    dataset,
    dataset_key: tuple[str, str],
    shade_root_directory: str,
    departure: datetime,
    start: GeoPoint,
    destination: GeoPoint,
    sun_penalty: float,
) -> RouteTimeView:
    artifact = resolve_shade_artifact(shade_root_directory, departure)
    timed = calculate_route_comparison_cached(
        dataset_key[0],
        dataset_key[1],
        str(artifact.directory),
        artifact.version,
        departure.isoformat(),
        start.latitude,
        start.longitude,
        destination.latitude,
        destination.longitude,
        sun_penalty,
    )
    disclosure = build_disclosure(
        dataset,
        None,
        timed.result.shade_optimized,
        departure,
        timed.calculated_at,
        precomputed_shade=True,
        daylight=timed.shade_time.daylight,
    )
    shortest_disclosure = build_disclosure(
        dataset,
        None,
        timed.result.shortest,
        departure,
        timed.calculated_at,
        precomputed_shade=True,
        daylight=timed.shade_time.daylight,
    )
    graph = dataset.payload.graph
    return RouteTimeView(
        departure=departure,
        disclosure=disclosure,
        shortest_disclosure=shortest_disclosure,
        comparison=timed.result,
        route_coordinates=_route_coordinates(
            graph, timed.result.shade_optimized.node_ids
        ),
        shortest_coordinates=_route_coordinates(graph, timed.result.shortest.node_ids),
        shade_timestamp=timed.shade_time.resolved.isoformat(),
        daylight=timed.shade_time.daylight,
        shade_load_seconds=timed.shade_load_seconds,
        route_seconds=timed.elapsed_seconds,
    )


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
initial_departure = datetime.combine(datetime.now(JST).date(), time(14, 0), JST)
initial_comparison = default_comparison_datetime(initial_departure)

with st.sidebar:
    st.header("経路条件")
    data_directory = st.text_input("加工済みデータ", str(DEFAULT_DATA))
    shade_root_directory = st.text_input(
        "事前計算済み日陰データ", str(DEFAULT_SHADE_DATA)
    )
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
    st.subheader("別時刻との比較")
    comparison_date = st.date_input(
        "比較日", value=initial_comparison.date(), key="comparison_date"
    )
    comparison_time = st.time_input(
        "比較時刻", value=initial_comparison.time(), key="comparison_time"
    )
    sun_penalty = st.slider("日向の距離ペナルティ", 1.0, 20.0, 10.0, 1.0)
    st.subheader("周辺施設")
    show_convenience = st.checkbox("コンビニ", value=True)
    show_drinking_water = st.checkbox("給水地点", value=True)
    calculate = st.button("2時刻を比較", type="primary", use_container_width=True)

st.info(
    "再計算範囲: 地点・ペナルティ変更は経路のみ、日時変更は事前計算値の"
    "時刻選択と経路、加工済みデータ変更は全処理を更新します。"
)

current_signature = (
    str(Path(data_directory).resolve()), start_latitude, start_longitude,
    destination_latitude, destination_longitude, departure_date, departure_time, sun_penalty,
    str(Path(shade_root_directory).resolve()),
    comparison_date, comparison_time,
)
area = None
try:
    dataset_path = Path(data_directory).resolve()
    manifest_path = dataset_path / "manifest.json"
    data_version = str(manifest_path.stat().st_mtime_ns)
    manifest = PreparedDatasetManifest.from_json(manifest_path)
    area = SearchArea(GeoPoint(**manifest.center), manifest.radius_m)
    shade_signatures = []
    for requested_date in (departure_date, comparison_date):
        shade_manifest = (
            Path(shade_root_directory).resolve()
            / requested_date.isoformat()
            / "manifest.json"
        )
        shade_signatures.append(
            str(shade_manifest.stat().st_mtime_ns)
            if shade_manifest.is_file()
            else f"missing:{requested_date.isoformat()}"
        )
    current_signature += (data_version, *shade_signatures)
except (OSError, ValueError) as error:
    clear_candidate()
    st.session_state.pop("map_scope", None)
    st.error(f"地図の対象範囲を読み込めません: {error}")

if calculate and area is not None:
    st.session_state.pop("route_snapshot", None)
    try:
        validate_selection(GeoPoint(start_latitude, start_longitude), area,
                           GeoPoint(destination_latitude, destination_longitude))
        validate_selection(GeoPoint(destination_latitude, destination_longitude), area,
                           GeoPoint(start_latitude, start_longitude))
        request_started = perf_counter()
        dataset_path = Path(data_directory).resolve()
        manifest_path = dataset_path / "manifest.json"
        data_version = str(manifest_path.stat().st_mtime_ns)
        departure = datetime.combine(departure_date, departure_time, JST)
        comparison_departure = datetime.combine(
            comparison_date, comparison_time, JST
        )
        validate_comparison_datetimes(departure, comparison_departure)
        inputs = UiInputs(
            str(dataset_path),
            GeoPoint(start_latitude, start_longitude),
            GeoPoint(destination_latitude, destination_longitude),
            departure,
            sun_penalty,
        )
        keys = recalculation_keys(inputs, data_version)
        dataset = load_dataset_cached(*keys.dataset)
        start = GeoPoint(start_latitude, start_longitude)
        destination = GeoPoint(destination_latitude, destination_longitude)
        base_view = _calculate_time_view(
            dataset,
            keys.dataset,
            shade_root_directory,
            departure,
            start,
            destination,
            sun_penalty,
        )
        comparison_view = _calculate_time_view(
            dataset,
            keys.dataset,
            shade_root_directory,
            comparison_departure,
            start,
            destination,
            sun_penalty,
        )
        total_seconds = perf_counter() - request_started
        st.session_state["route_snapshot"] = (
            current_signature,
            base_view,
            comparison_view,
            total_seconds,
        )
    except (OSError, ValueError, RouteNotFoundError) as error:
        st.error(str(error))

snapshot = st.session_state.get("route_snapshot")
coordinates = ()
shortest_coordinates = ()
comparison_coordinates = ()
comparison_shortest_coordinates = ()
if snapshot and snapshot[0] == current_signature:
    _, base_view, comparison_view, total_seconds = snapshot
    coordinates = base_view.route_coordinates
    shortest_coordinates = base_view.shortest_coordinates
    comparison_coordinates = comparison_view.route_coordinates
    comparison_shortest_coordinates = comparison_view.shortest_coordinates
    st.subheader("2時刻のルート比較")
    st.markdown(
        "| 指標 | 基準・最短 | 基準・日陰優先 | 比較・最短 | 比較・日陰優先 |\n"
        "|---|---:|---:|---:|---:|\n"
        f"| 距離 | {base_view.shortest_disclosure.route_distance_m:,.0f} m | "
        f"{base_view.disclosure.route_distance_m:,.0f} m | "
        f"{comparison_view.shortest_disclosure.route_distance_m:,.0f} m | "
        f"{comparison_view.disclosure.route_distance_m:,.0f} m |\n"
        f"| 推定徒歩時間 | {base_view.comparison.shortest.estimated_walk_minutes} 分 | "
        f"{base_view.comparison.shade_optimized.estimated_walk_minutes} 分 | "
        f"{comparison_view.comparison.shortest.estimated_walk_minutes} 分 | "
        f"{comparison_view.comparison.shade_optimized.estimated_walk_minutes} 分 |\n"
        f"| 推定日向距離 | {base_view.shortest_disclosure.sunny_distance_m:,.0f} m | "
        f"{base_view.disclosure.sunny_distance_m:,.0f} m | "
        f"{comparison_view.shortest_disclosure.sunny_distance_m:,.0f} m | "
        f"{comparison_view.disclosure.sunny_distance_m:,.0f} m |\n"
        f"| 推定日陰率 | {base_view.shortest_disclosure.shade_ratio_pct:.1f}% | "
        f"{base_view.disclosure.shade_ratio_pct:.1f}% | "
        f"{comparison_view.shortest_disclosure.shade_ratio_pct:.1f}% | "
        f"{comparison_view.disclosure.shade_ratio_pct:.1f}% |"
    )
    first, second, third, fourth = st.columns(4)
    first.metric("距離増加", f"{base_view.comparison.distance_increase_m:+,.0f} m")
    second.metric(
        "比較時刻の距離増加",
        f"{comparison_view.comparison.distance_increase_m:+,.0f} m",
    )
    third.metric(
        "日陰優先の日陰率変化",
        f"{comparison_view.disclosure.shade_ratio_pct - base_view.disclosure.shade_ratio_pct:+.1f} ポイント",
    )
    fourth.metric("前回の2時刻計算", f"{total_seconds:.3f} 秒")
    st.caption(
        "地図凡例: 基準は緑実線（日陰優先）・赤破線（最短）、"
        "比較は青実線（日陰優先）・橙破線（最短）。"
        "推定徒歩時間は80m/分で算出しています。差が0の場合は同一ルートです。"
    )
    with st.expander("計算根拠・時刻・データ情報", expanded=True):
        for label, view in (("基準", base_view), ("比較", comparison_view)):
            st.write(f"{label}の要求日時: `{view.disclosure.departure_iso}`")
            st.write(f"{label}で使用した事前計算時刻: `{view.shade_timestamp}`")
            st.write(
                f"{label}の太陽状態: "
                f"{'昼間' if view.daylight else '夜間（直達日射なし）'}"
            )
            st.write(
                f"{label}の内訳（未キャッシュ計算時）: 日陰データ読込 "
                f"{view.shade_load_seconds:.3f}秒 / 経路 {view.route_seconds:.3f}秒"
            )
        st.write(f"データ取得処理日時: `{base_view.disclosure.data_acquired_at}`")
        st.write(
            f"データ出典: {base_view.disclosure.data_source} / "
            "© OpenStreetMap contributors"
        )
        st.write(f"データ範囲: `{base_view.disclosure.data_scope}`")
        st.write(
            f"計算条件: 日向の距離ペナルティ {sun_penalty:.1f} / "
            "徒歩速度 80m/分"
        )
    warnings = dict.fromkeys(
        base_view.disclosure.warnings + comparison_view.disclosure.warnings
    )
    for warning in warnings:
        st.warning(warning)
elif snapshot:
    st.warning("条件が変更されたため、前回の経路を非表示にしました。「2時刻を比較」で更新してください。")
else:
    st.write("サイドバーで条件を確認し、「2時刻を比較」を押してください。")

if area is not None:
    facilities = ()
    try:
        all_facilities = load_facilities_cached(str(dataset_path), data_version)
        enabled = set()
        if show_convenience:
            enabled.add("convenience")
        if show_drinking_water:
            enabled.add("drinking_water")
        facilities = tuple(item for item in all_facilities if item.kind in enabled)
        convenience_count = sum(item.kind == "convenience" for item in all_facilities)
        water_count = sum(item.kind == "drinking_water" for item in all_facilities)
        st.caption(
            f"周辺施設（加工済みデータ）: コンビニ {convenience_count}件 / "
            f"給水地点 {water_count}件"
        )
        st.caption(
            f"出典: {manifest.attribution} / データ取得処理日時: "
            f"{manifest.acquired_at_utc}。OSMの登録状況と取得時点に依存し、"
            "営業・利用可能であることを保証しません。"
        )
    except (OSError, ValueError) as error:
        st.warning(f"周辺施設を読み込めません: {error}")
    render_picker(
        area,
        (str(dataset_path), data_version),
        coordinates,
        shortest_coordinates,
        facilities,
        comparison_coordinates,
        comparison_shortest_coordinates,
    )
