import streamlit as st
from streamlit_folium import st_folium
import osmnx as ox
import networkx as nx
import folium
import geopandas as gpd
from shapely.geometry import MultiPoint, LineString, Point 
from shapely.ops import unary_union
from pysolar.solar import get_altitude, get_azimuth
from datetime import datetime, timezone
import math
import pandas as pd
from shapely.errors import ShapelyDeprecationWarning
import warnings

# 余計な警告を消す
warnings.filterwarnings("ignore", category=ShapelyDeprecationWarning) 

# -------------------------------------------
# 1. 設定とデータ読み込み
# -------------------------------------------
@st.cache_resource
def load_data():
    point = (34.2325, 135.1917)
    dist = 1000 
    
    G = ox.graph_from_point(point, dist=dist, network_type='walk')
    G = ox.truncate.largest_component(G, strongly=True)
    buildings = ox.features_from_point(point, tags={'building': True}, dist=dist)
    
    if 'height' not in buildings.columns:
        buildings['height'] = 10.0
    else:
        buildings['height'] = pd.to_numeric(buildings['height'], errors='coerce').fillna(10.0)
    
    buildings_proj = buildings.to_crs(epsg=6676)
    G_proj = ox.project_graph(G, to_crs='epsg:6676')
    
    return G, buildings, G_proj, buildings_proj, point

st.set_page_config(layout="wide", page_title="Shadow Navi Pro")
st.title("☀Shadow Navi")

with st.spinner('地図データを読み込み中...'):
    G, buildings, G_proj, buildings_proj, center_point = load_data()

# -------------------------------------------
# 2. サイドバー設定
# -------------------------------------------
st.sidebar.header("環境設定")
date_input = st.sidebar.date_input("日付", datetime(2024, 8, 1))
time_input = st.sidebar.time_input("時刻", datetime(2024, 8, 1, 14, 0).time())

# ★新機能：気温の設定
temp_input = st.sidebar.slider("現在の気温 (℃)", 20, 40, 32)
sun_penalty = st.sidebar.slider("日向の避けやすさ", 1.0, 20.0, 10.0)

if st.sidebar.button("リセット"):
    st.session_state['start_point'] = None
    st.session_state['end_point'] = None
    st.session_state['last_clicked_coords'] = None
    st.rerun()

# -------------------------------------------
# 3. 影の計算
# -------------------------------------------
dt_jst = datetime.combine(date_input, time_input)
dt_utc = dt_jst.replace(tzinfo=timezone.utc) - pd.Timedelta(hours=9)

lat, lon = center_point
altitude = get_altitude(lat, lon, dt_utc)
azimuth = get_azimuth(lat, lon, dt_utc)

shadow_polygons = []
if altitude > 0:
    shadow_len_factor = 1 / math.tan(math.radians(altitude))
    azimuth_math = math.radians(azimuth - 180)
    dx = shadow_len_factor * math.sin(azimuth_math)
    dy = shadow_len_factor * math.cos(azimuth_math)
    
    for _, row in buildings_proj.iterrows():
        if row.geometry.geom_type == 'Polygon':
            h = row['height']
            x, y = row.geometry.exterior.coords.xy
            ground = list(zip(x, y))
            roof = [(xi + h*dx, yi + h*dy) for xi, yi in zip(x, y)]
            shadow_poly = MultiPoint(ground + roof).convex_hull
            shadow_polygons.append(shadow_poly)

all_shadows = unary_union(shadow_polygons) if shadow_polygons else None

# -------------------------------------------
# 4. 地図とロジック
# -------------------------------------------
if 'start_point' not in st.session_state:
    st.session_state['start_point'] = None
if 'end_point' not in st.session_state:
    st.session_state['end_point'] = None

# モード選択
col_mode, col_msg = st.columns([1, 3])
with col_mode:
    mode = st.radio("📍 設定モード", ["スタート地点", "ゴール地点"], horizontal=True)
with col_msg:
    if mode == "スタート地点":
        st.info("地図をクリックして **スタート（緑）** を設置")
    else:
        st.info("地図をクリックして **ゴール（赤）** を設置")

m = folium.Map(location=center_point, zoom_start=16)

if all_shadows:
    shadows_gdf = gpd.GeoDataFrame(geometry=[all_shadows], crs=buildings_proj.crs).to_crs(epsg=4326)
    folium.GeoJson(
        shadows_gdf,
        style_function=lambda x: {'fillColor': 'black', 'color': 'none', 'fillOpacity': 0.5},
        name="日陰"
    ).add_to(m)

if st.session_state['start_point']:
    folium.Marker(st.session_state['start_point'], icon=folium.Icon(color='green', icon='play'), tooltip="Start").add_to(m)
if st.session_state['end_point']:
    folium.Marker(st.session_state['end_point'], icon=folium.Icon(color='red', icon='flag'), tooltip="Goal").add_to(m)

# -------------------------------------------
# ★ ルート計算とリスク診断ロジック
# -------------------------------------------
if st.session_state['start_point'] and st.session_state['end_point']:
    orig = ox.distance.nearest_nodes(G, X=st.session_state['start_point'][1], Y=st.session_state['start_point'][0])
    dest = ox.distance.nearest_nodes(G, X=st.session_state['end_point'][1], Y=st.session_state['end_point'][0])
    
    # エッジごとの計算
    for u, v, k, data in G_proj.edges(keys=True, data=True):
        length = data['length']
        if 'geometry' in data:
            mid = data['geometry'].interpolate(0.5, normalized=True)
        else:
            p1, p2 = G_proj.nodes[u], G_proj.nodes[v]
            mid = Point((p1['x'] + p2['x'])/2, (p1['y'] + p2['y'])/2)
        
        is_shaded = False
        if all_shadows and all_shadows.contains(mid):
            is_shaded = True
        
        # 情報を保存しておく（後で集計するため）
        data['is_shaded'] = is_shaded
        data['shadow_cost'] = length if is_shaded else length * sun_penalty

    try:
        route = nx.shortest_path(G_proj, orig, dest, weight='shadow_cost')
        
        if len(route) >= 2:
            route_coords = [(G.nodes[n]['y'], G.nodes[n]['x']) for n in route]
            folium.PolyLine(locations=route_coords, color="cyan", weight=6, opacity=0.8).add_to(m)
            
            # ★集計ロジック：日向と日陰の距離を計算
            total_dist = 0
            sunny_dist = 0
            shaded_dist = 0
            
            # ルート上のエッジを一つずつチェック
            for u, v in zip(route[:-1], route[1:]):
                # 複数の道がある場合、一番短いものを選ぶ（簡易処理）
                edge_data = min(G_proj[u][v].values(), key=lambda x: x['length'])
                dist = edge_data['length']
                total_dist += dist
                
                if edge_data.get('is_shaded', False):
                    shaded_dist += dist
                else:
                    sunny_dist += dist

            # ★日向率の計算
            sunny_ratio = (sunny_dist / total_dist) * 100 if total_dist > 0 else 0
            
            # ★リスク判定ロジック（簡易版）
            # 気温30度以上かつ日向距離が長いと危険
            risk_level = "安全"
            risk_color = "green"
            advice = "快適なルートです。"

            if temp_input >= 35: # 猛暑日
                if sunny_dist > 500:
                    risk_level = "危険！"
                    risk_color = "red"
                    advice = "日向が500m以上あります。外出を控えるか、タクシー推奨です。"
                elif sunny_dist > 200:
                    risk_level = "厳重警戒"
                    risk_color = "orange"
                    advice = "極めて暑いです。必ず水分を持ってください。"
                else:
                    risk_level = "警戒"
                    risk_color = "gold"
                    advice = "短距離ですが、油断せず移動してください。"
            
            elif temp_input >= 30: # 真夏日
                if sunny_dist > 1000:
                    risk_level = "厳重警戒"
                    risk_color = "orange"
                    advice = "日向が1km以上あります。こまめな休憩が必要です。"
                elif sunny_dist > 500:
                    risk_level = "警戒"
                    risk_color = "gold"
                    advice = "汗をかきます。水分補給をしてください。"
                else:
                    risk_level = "注意"
                    risk_color = "blue"
                    advice = "比較的安全ですが、熱中症に注意してください。"
            
            # ★結果の表示（メトリクス）
            st.markdown("### ルート診断結果")
            m1, m2, m3 = st.columns(3)
            m1.metric("総距離", f"{int(total_dist)} m")
            m2.metric("日陰の割合", f"{100 - int(sunny_ratio)} %")
            m3.metric("日向の距離", f"{int(sunny_dist)} m", delta_color="inverse")
            
            # ★アラート表示
            st.markdown(f"""
            <div style="padding: 15px; border-radius: 10px; background-color: {risk_color}; color: white; text-align: center; margin-bottom: 10px;">
                <h3 style="margin:0;">判定: {risk_level}</h3>
                <p style="margin:0;">{advice}</p>
            </div>
            """, unsafe_allow_html=True)

        else:
            st.warning("スタートとゴールが近すぎます。")
            
    except nx.NetworkXNoPath:
        st.error("ルートが見つかりませんでした。")

# 地図表示
output = st_folium(m, width=1000, height=600)

if output['last_clicked']:
    new_coords = (output['last_clicked']['lat'], output['last_clicked']['lng'])
    if new_coords != st.session_state.get('last_clicked_coords'):
        st.session_state['last_clicked_coords'] = new_coords
        if mode == "スタート地点":
            st.session_state['start_point'] = new_coords
        elif mode == "ゴール地点":
            st.session_state['end_point'] = new_coords
        st.rerun()