"""Session-based map input. This module never invokes data/shadow/route loading."""

import folium
import streamlit as st
from streamlit_folium import st_folium

from ..geocoding import SearchArea
from ..map_selection import validate_selection
from ..models import GeoPoint


def clear_candidate() -> None:
    generation = st.session_state.get("map_generation", 0)
    st.session_state.pop(f"map_picker_{generation}", None)
    st.session_state.pop("map_pending", None)
    st.session_state.pop("map_error", None)
    st.session_state.pop("map_last_click", None)
    st.session_state["map_generation"] = generation + 1


def confirm_candidate(area: SearchArea) -> None:
    point = st.session_state.get("map_pending")
    if point is None:
        return
    role = st.session_state["map_role"]
    other = "destination" if role == "start" else "start"
    try:
        validate_selection(point, area, GeoPoint(
            st.session_state[f"{other}_latitude"],
            st.session_state[f"{other}_longitude"],
        ))
    except ValueError as error:
        st.session_state["map_error"] = str(error)
        return
    st.session_state[f"{role}_latitude"] = point.latitude
    st.session_state[f"{role}_longitude"] = point.longitude
    clear_candidate()


def receive_event(key: str, area: SearchArea) -> None:
    event = st.session_state.get(key) or {}
    if event.get("center"):
        st.session_state["map_center"] = event["center"]
    if event.get("zoom") is not None:
        st.session_state["map_zoom"] = event["zoom"]
    clicked = event.get("last_clicked")
    if not clicked or clicked == st.session_state.get("map_last_click"):
        return
    st.session_state["map_last_click"] = clicked
    st.session_state.pop("map_pending", None)
    st.session_state.pop("map_error", None)
    try:
        point = GeoPoint(clicked["lat"], clicked["lng"])
        other = "destination" if st.session_state["map_role"] == "start" else "start"
        validate_selection(point, area, GeoPoint(
            st.session_state[f"{other}_latitude"],
            st.session_state[f"{other}_longitude"],
        ))
        st.session_state["map_pending"] = point
    except (ValueError, KeyError, TypeError) as error:
        st.session_state["map_error"] = f"地点を選択できません: {error}"


def render_picker(area: SearchArea, scope_key: tuple, coordinates=()) -> None:
    if st.session_state.get("map_scope") != scope_key:
        clear_candidate()
        st.session_state["map_scope"] = scope_key
        st.session_state["map_center"] = {"lat": area.center.latitude, "lng": area.center.longitude}
        st.session_state["map_zoom"] = 15
    st.subheader("地図から地点を選択")
    st.radio("変更する地点", ["start", "destination"], key="map_role",
             format_func=lambda role: "出発地" if role == "start" else "目的地",
             horizontal=True, on_change=clear_candidate)
    st.caption("地図クリック → 候補を地点へ反映 → サイドバーの「経路を計算」。円はデータの対象範囲です。")
    pending = st.session_state.get("map_pending")
    if pending:
        st.write(f"候補: {pending.latitude:.6f}, {pending.longitude:.6f}")
    if st.session_state.get("map_error"):
        st.warning(st.session_state["map_error"])
    left, right = st.columns(2)
    left.button("候補を地点へ反映", key="map_confirm", disabled=pending is None,
                on_click=confirm_candidate, args=(area,))
    right.button("候補を取消・再選択", key="map_cancel", on_click=clear_candidate)
    # Keep the base script stable; replace only the dynamic FeatureGroup.
    base = folium.Map(location=[area.center.latitude, area.center.longitude], zoom_start=15)
    features = folium.FeatureGroup(name="地点と経路")
    folium.Circle([area.center.latitude, area.center.longitude], radius=area.radius_m,
                  color="#777777", fill=False, tooltip="データ対象範囲").add_to(features)
    for role, label, color in [("start", "出発地", "blue"), ("destination", "目的地", "red")]:
        try:
            point = GeoPoint(st.session_state[f"{role}_latitude"], st.session_state[f"{role}_longitude"])
        except ValueError:
            st.warning(f"{label}の緯度経度を確認してください。")
            continue
        folium.Marker([point.latitude, point.longitude],
                      tooltip=label, icon=folium.Icon(color=color)).add_to(features)
    if pending:
        folium.Marker([pending.latitude, pending.longitude], tooltip="未確定の候補",
                      icon=folium.Icon(color="orange")).add_to(features)
    if len(coordinates) >= 2:
        folium.PolyLine(coordinates, color="#167d4a", weight=7).add_to(features)
    key = f"map_picker_{st.session_state['map_generation']}"
    st_folium(base, key=key, height=460, use_container_width=True,
              returned_objects=["last_clicked", "center", "zoom"],
              center=st.session_state["map_center"], zoom=st.session_state["map_zoom"],
              feature_group_to_add=features, on_change=lambda: receive_event(key, area))
