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

# 余計な警告を消す設定
warnings.filterwarnings("ignore", category=ShapelyDeprecationWarning) 

# -------------------------------------------
# 1. 設定とデータ読み込み（キャッシュ化）
# -------------------------------------------
@st.cache_resource
def load_data():
    # 和歌山駅周辺
    point = (34.2325, 135.1917)
    dist = 1000 # 範囲を1kmに設定
    
    # 道路データを取得
    G = ox.graph_from_point(point, dist=dist, network_type='walk')
    # 孤立点を除去（新しい書き方）
    G = ox.truncate.largest_component(G, strongly=True)

    # 建物データを取得
    buildings = ox.features_from_point(point, tags={'building': True}, dist=dist)
    
    # 高さデータの前処理
    if 'height' not in buildings.columns:
        buildings['height'] = 10.0
    else:
        buildings['height'] = pd.to_numeric(buildings['height'], errors='coerce').fillna(10.0)
    
    # 座標変換（メートル単位）
    buildings_proj = buildings.to_crs(epsg=6676)
    G_proj = ox.project_graph(G, to_crs='epsg:6676')
    
    return G, buildings, G_proj, buildings_proj, point

# ページ設定（ワイド表示）
st.set_page_config(layout="wide", page_title="Shadow Navi")

st.title("☀Shadow Navi WAKAYAMA")

# データをロード
with st.spinner('地図データを読み込み中...'):
    G, buildings, G_proj, buildings_proj, center_point = load_data()

# -------------------------------------------
# 2. サイドバー設定
# -------------------------------------------
st.sidebar.header("設定")
date_input = st.sidebar.date_input("日付", datetime(2024, 8, 1))
time_input = st.sidebar.time_input("時刻", datetime(2024, 8, 1, 14, 0).time())
sun_penalty = st.sidebar.slider("日向の避けやすさ", 1.0, 20.0, 10.0)

# リセットボタン
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
# 4. メイン画面：地図と操作
# -------------------------------------------
# セッション状態の初期化
if 'start_point' not in st.session_state:
    st.session_state['start_point'] = None
if 'end_point' not in st.session_state:
    st.session_state['end_point'] = None

# モード選択
col_mode, col_msg = st.columns([1, 3])
with col_mode:
    mode = st.radio(
        "📍 設定モード",
        ["スタート地点", "ゴール地点"],
        horizontal=True
    )
with col_msg:
    if mode == "スタート地点":
        st.info("地図をクリックすると、そこに **スタート（緑）** がセットされます。")
    else:
        st.info("地図をクリックすると、そこに **ゴール（赤）** がセットされます。")

# 地図の作成
m = folium.Map(location=center_point, zoom_start=16)

# 影の描画
if all_shadows:
    shadows_gdf = gpd.GeoDataFrame(geometry=[all_shadows], crs=buildings_proj.crs).to_crs(epsg=4326)
    folium.GeoJson(
        shadows_gdf,
        style_function=lambda x: {'fillColor': 'black', 'color': 'none', 'fillOpacity': 0.5},
        name="日陰"
    ).add_to(m)

# マーカーの描画
if st.session_state['start_point']:
    folium.Marker(
        st.session_state['start_point'], 
        icon=folium.Icon(color='green', icon='play'), 
        tooltip="Start"
    ).add_to(m)

if st.session_state['end_point']:
    folium.Marker(
        st.session_state['end_point'], 
        icon=folium.Icon(color='red', icon='flag'), 
        tooltip="Goal"
    ).add_to(m)

# ルート計算と描画
if st.session_state['start_point'] and st.session_state['end_point']:
    # 最寄りノード探索
    orig = ox.distance.nearest_nodes(G, X=st.session_state['start_point'][1], Y=st.session_state['start_point'][0])
    dest = ox.distance.nearest_nodes(G, X=st.session_state['end_point'][1], Y=st.session_state['end_point'][0])
    
    # コスト計算
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
            
        data['shadow_cost'] = length if is_shaded else length * sun_penalty

    # パス探索
    try:
        route = nx.shortest_path(G_proj, orig, dest, weight='shadow_cost')
        
        if len(route) >= 2:
            route_coords = [(G.nodes[n]['y'], G.nodes[n]['x']) for n in route]
            folium.PolyLine(
                locations=route_coords,
                color="cyan", weight=6, opacity=0.8,
                tooltip="日陰ルート"
            ).add_to(m)
            
            # ★★★ ここを修正しました（route_to_gdfを使用） ★★★
            route_gdf = ox.routing.route_to_gdf(G_proj, route)
            total_dist = int(route_gdf['length'].sum())
            
            st.success(f"ルートが見つかりました！ (距離: 約{total_dist}m)")
        else:
            st.warning("スタートとゴールが近すぎます。")
            
    except nx.NetworkXNoPath:
        st.error("ルートが見つかりませんでした。エリア外か、つながっていない道です。")


# クリックイベントの処理
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