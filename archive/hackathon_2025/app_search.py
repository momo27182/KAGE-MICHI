import streamlit as st
from streamlit_folium import st_folium
import osmnx as ox
import networkx as nx
import folium
import geopandas as gpd
from shapely.geometry import MultiPoint, LineString, Point 
from shapely.ops import unary_union
from pysolar.solar import get_altitude, get_azimuth
from datetime import datetime, timezone, timedelta
import math
import pandas as pd
from shapely.errors import ShapelyDeprecationWarning
import warnings
from geopy.geocoders import Nominatim 
from geopy.exc import GeocoderTimedOut

# 警告抑制
warnings.filterwarnings("ignore", category=ShapelyDeprecationWarning) 

# ==========================================
# 1. データ読み込みと関数定義
# ==========================================

@st.cache_resource
def load_data():
    point = (34.2325, 135.1917) # 和歌山駅
    dist = 1700 # 半径3km
    
    G = ox.graph_from_point(point, dist=dist, network_type='walk')
    G = ox.truncate.largest_component(G, strongly=True)
    
    buildings = ox.features_from_point(point, tags={'building': True}, dist=dist)
    if 'height' not in buildings.columns:
        buildings['height'] = 10.0
    else:
        buildings['height'] = pd.to_numeric(buildings['height'], errors='coerce').fillna(10.0)
    
    spots = ox.features_from_point(point, tags={'shop': 'convenience', 'amenity': 'drinking_water'}, dist=dist)
    
    buildings_proj = buildings.to_crs(epsg=6676)
    G_proj = ox.project_graph(G, to_crs='epsg:6676')
    
    return G, buildings, spots, G_proj, buildings_proj, point

def create_shadow_polygon(buildings_proj, dt_utc, center_point):
    lat, lon = center_point
    altitude = get_altitude(lat, lon, dt_utc)
    azimuth = get_azimuth(lat, lon, dt_utc)

    if altitude <= 0: return None

    shadow_len_factor = 1 / math.tan(math.radians(altitude))
    azimuth_math = math.radians(azimuth - 180)
    dx = shadow_len_factor * math.sin(azimuth_math)
    dy = shadow_len_factor * math.cos(azimuth_math)
    
    polygons = []
    for _, row in buildings_proj.iterrows():
        if row.geometry.geom_type == 'Polygon':
            h = row['height']
            x, y = row.geometry.exterior.coords.xy
            ground = list(zip(x, y))
            roof = [(xi + h*dx, yi + h*dy) for xi, yi in zip(x, y)]
            polygons.append(MultiPoint(ground + roof).convex_hull)
            
    return unary_union(polygons) if polygons else None

def solve_route(G_proj, orig, dest, all_shadows, sun_penalty):
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
        
        data['is_shaded'] = is_shaded
        data['shadow_cost'] = length if is_shaded else length * sun_penalty

    try:
        route = nx.shortest_path(G_proj, orig, dest, weight='shadow_cost')
        if len(route) < 2: return None
        
        total_dist = 0
        sunny_dist = 0
        for u, v in zip(route[:-1], route[1:]):
            edge_data = min(G_proj[u][v].values(), key=lambda x: x['length'])
            dist = edge_data['length']
            total_dist += dist
            if not edge_data.get('is_shaded', False):
                sunny_dist += dist
                
        sunny_ratio = (sunny_dist / total_dist) * 100 if total_dist > 0 else 0
        return route, total_dist, sunny_ratio, sunny_dist
        
    except nx.NetworkXNoPath:
        return None

# ★★★ 修正: 粘り強く検索する関数 ★★★
def get_location_candidates(address):
    geolocator = Nominatim(user_agent="kage_michi_app")
    
    # 検索パターンのリスト：上から順に試します
    search_queries = []
    
    # パターン1: 「和歌山市」をつけて詳しく (基本)
    if "和歌山市" not in address:
        search_queries.append(f"和歌山県和歌山市 {address}")
    
    # パターン2: 「和歌山県」だけで少し緩く
    if "和歌山県" not in address:
        search_queries.append(f"和歌山県 {address}")
        
    # パターン3: 入力された文字そのままで (「JR和歌山駅」などはこれでヒットするかも)
    search_queries.append(address)

    # 順番に検索を実行
    for query in search_queries:
        try:
            # limit=30 で多めに取得
            locations = geolocator.geocode(query, exactly_one=False, limit=30)
            
            if locations:
                # 見つかったらその時点で結果を返して終了！
                return [(loc.address, (loc.latitude, loc.longitude)) for loc in locations]
                
        except GeocoderTimedOut:
            continue
            
    # 全部試してダメだった場合
    return []
    
# ==========================================
# 2. アプリ画面構築
# ==========================================

st.set_page_config(layout="wide", page_title="KAGE-MICHI Ultimate")
st.title("KAGE-MICHI")

with st.spinner('広域地図データ(半径1km)を読み込み中...'):
    G, buildings, spots, G_proj, buildings_proj, center_point = load_data()

# セッション状態の初期化
if 'start_point' not in st.session_state: st.session_state['start_point'] = None
if 'end_point' not in st.session_state: st.session_state['end_point'] = None
if 'map_center' not in st.session_state: st.session_state['map_center'] = [center_point[0], center_point[1]]
if 'map_zoom' not in st.session_state: st.session_state['map_zoom'] = 15

# 候補リストを保存する場所
if 'start_candidates' not in st.session_state: st.session_state['start_candidates'] = []
if 'end_candidates' not in st.session_state: st.session_state['end_candidates'] = []

# サイドバー設定
st.sidebar.header("📍 ルート検索")

st.sidebar.markdown("### 1. 地名を入力")
start_input = st.sidebar.text_input("出発地", placeholder="例: JR和歌山駅")
end_input = st.sidebar.text_input("目的地", placeholder="例: 和歌山城")

# ★ステップ1: 候補を検索するボタン
if st.sidebar.button("🔍 候補を検索"):
    if start_input and end_input:
        with st.sidebar.status("場所を探しています..."):
            st.session_state['start_candidates'] = get_location_candidates(start_input)
            st.session_state['end_candidates'] = get_location_candidates(end_input)
            
            if not st.session_state['start_candidates']:
                st.sidebar.error(f"「{start_input}」が見つかりませんでした。")
            if not st.session_state['end_candidates']:
                st.sidebar.error(f"「{end_input}」が見つかりませんでした。")

# ★ステップ2: 候補から選ぶ（候補がある場合のみ表示）
selected_start_coords = None
selected_end_coords = None

if st.session_state['start_candidates']:
    st.sidebar.markdown("### 2. 場所を選択")
    # 選択肢の作成（住所を表示）
    start_options = {name: coords for name, coords in st.session_state['start_candidates']}
    selected_start_name = st.sidebar.selectbox("出発地の候補", list(start_options.keys()))
    selected_start_coords = start_options[selected_start_name]

if st.session_state['end_candidates']:
    end_options = {name: coords for name, coords in st.session_state['end_candidates']}
    selected_end_name = st.sidebar.selectbox("目的地の候補", list(end_options.keys()))
    selected_end_coords = end_options[selected_end_name]

# ★ステップ3: 確定してルート検索
if selected_start_coords and selected_end_coords:
    if st.sidebar.button("🚀 このルートで検索"):
        st.session_state['start_point'] = selected_start_coords
        st.session_state['end_point'] = selected_end_coords
        
        # 地図の中心を合わせる
        mid_lat = (selected_start_coords[0] + selected_end_coords[0]) / 2
        mid_lon = (selected_start_coords[1] + selected_end_coords[1]) / 2
        st.session_state['map_center'] = [mid_lat, mid_lon]
        st.session_state['map_zoom'] = 14
        st.rerun()


st.sidebar.markdown("---")
st.sidebar.header("環境設定")
date_input = st.sidebar.date_input("日付", datetime(2024, 8, 1))
time_input = st.sidebar.time_input("時刻", datetime(2024, 8, 1, 14, 0).time())
temp_input = st.sidebar.slider("気温 (℃)", 20, 40, 32)
sun_penalty = st.sidebar.slider("日向の避けやすさ", 1.0, 20.0, 10.0)
show_spots = st.sidebar.checkbox("コンビニ・給水スポットを表示", value=True)

if st.sidebar.button("リセット"):
    st.session_state.clear()
    st.rerun()

dt_jst = datetime.combine(date_input, time_input)
dt_utc = dt_jst.replace(tzinfo=timezone.utc) - pd.Timedelta(hours=9)
all_shadows = create_shadow_polygon(buildings_proj, dt_utc, center_point)

col_mode, col_msg = st.columns([1, 3])
with col_mode:
    mode = st.radio("📍 クリック設定モード", ["スタート", "ゴール"], horizontal=True)
with col_msg:
    st.info(f"地名検索、または地図をクリックして **{mode}（{'緑' if mode=='スタート' else '赤'}）** を設置してください。")

# 地図生成
m = folium.Map(location=st.session_state['map_center'], zoom_start=st.session_state['map_zoom'])

if all_shadows:
    folium.GeoJson(gpd.GeoDataFrame(geometry=[all_shadows], crs=buildings_proj.crs).to_crs(epsg=4326),
                   style_function=lambda x: {'fillColor': 'black', 'color': 'none', 'fillOpacity': 0.5}).add_to(m)

if show_spots and not spots.empty:
    for _, row in spots.iterrows():
        loc = [row.geometry.y, row.geometry.x] if row.geometry.geom_type == 'Point' else [row.geometry.centroid.y, row.geometry.centroid.x]
        icon = 'shopping-cart' if row.get('shop')=='convenience' else 'tint'
        color = 'orange' if row.get('shop')=='convenience' else 'blue'
        folium.Marker(loc, icon=folium.Icon(color=color, icon=icon, prefix='fa')).add_to(m)

if st.session_state['start_point']:
    folium.Marker(st.session_state['start_point'], icon=folium.Icon(color='green', icon='play'), popup="Start").add_to(m)
if st.session_state['end_point']:
    folium.Marker(st.session_state['end_point'], icon=folium.Icon(color='red', icon='flag'), popup="Goal").add_to(m)

# ==========================================
# 3. ルート計算・予測
# ==========================================
if st.session_state['start_point'] and st.session_state['end_point']:
    orig = ox.distance.nearest_nodes(G, X=st.session_state['start_point'][1], Y=st.session_state['start_point'][0])
    dest = ox.distance.nearest_nodes(G, X=st.session_state['end_point'][1], Y=st.session_state['end_point'][0])
    
    result_now = solve_route(G_proj, orig, dest, all_shadows, sun_penalty)
    
    if result_now:
        route, total_dist, sunny_ratio, sunny_dist = result_now
        
        route_coords = [(G.nodes[n]['y'], G.nodes[n]['x']) for n in route]
        folium.PolyLine(locations=route_coords, color="cyan", weight=6, opacity=0.8).add_to(m)
        
        walk_minutes = math.ceil(total_dist / 80)
        
        st.markdown("### 診断結果")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("所要時間", f"徒歩 {walk_minutes} 分", f"{int(total_dist)} m")
        c2.metric("日陰率", f"{100 - int(sunny_ratio)} %")
        c3.metric("日向の距離", f"{int(sunny_dist)} m", delta_color="inverse")
        
        risk_level = "安全"
        risk_color = "green"
        advice = "快適なルートです。"

        if temp_input >= 35: 
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
        
        elif temp_input >= 30:
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

        st.markdown(f"""
        <div style="padding: 15px; border-radius: 10px; background-color: {risk_color}; color: white; text-align: center; margin-bottom: 10px;">
            <h3 style="margin:0;">判定: {risk_level}</h3>
            <p style="margin:0;">{advice}</p>
        </div>
        """, unsafe_allow_html=True)

        st.write("---")
        
        st.subheader("予測: 時間をずらすとどうなる？")
        col_btn, col_res = st.columns([1, 3])
        with col_btn:
            predict_btn = st.button("1時間後の状況を計算する")
            
        if predict_btn:
            with col_res:
                with st.spinner("1時間後の太陽位置と影を再計算中..."):
                    dt_next = dt_utc + timedelta(hours=1)
                    shadow_next = create_shadow_polygon(buildings_proj, dt_next, center_point)
                    result_next = solve_route(G_proj, orig, dest, shadow_next, sun_penalty)
                    
                    if result_next:
                        _, _, sunny_ratio_next, _ = result_next
                        shade_ratio_now = 100 - sunny_ratio
                        shade_ratio_next = 100 - sunny_ratio_next
                        diff = shade_ratio_next - shade_ratio_now
                        
                        st.markdown(f"#### 1時間後 ({dt_jst.hour + 1}:00) の日陰率: **{int(shade_ratio_next)}%**")
                        if diff > 5:
                            st.success(f"今より {int(diff)}% 涼しくなります！** カフェで少し休んでから行くのが賢い選択です。")
                        elif diff < -5:
                            st.error(f"今より {int(abs(diff))}% 暑くなります！** すぐに出発しましょう！")
                        else:
                            st.info("あまり変わりません。好きなタイミングで行きましょう。")
    else:
        st.error("ルートが見つかりませんでした。")

output = st_folium(m, width=1000, height=600, returned_objects=["last_clicked", "center", "zoom"])

if output['center']:
    st.session_state['map_center'] = [output['center']['lat'], output['center']['lng']]
if output['zoom']:
    st.session_state['map_zoom'] = output['zoom']

if output['last_clicked']:
    new_coords = (output['last_clicked']['lat'], output['last_clicked']['lng'])
    if new_coords != st.session_state.get('last_clicked_coords'):
        st.session_state['last_clicked_coords'] = new_coords
        if mode == "スタート": st.session_state['start_point'] = new_coords
        elif mode == "ゴール": st.session_state['end_point'] = new_coords
        st.rerun()