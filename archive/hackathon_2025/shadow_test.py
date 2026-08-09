import osmnx as ox
import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from shapely.geometry import Polygon
from pysolar.solar import get_altitude, get_azimuth
from datetime import datetime, timezone
import math

# ---------------------------------------------
# 1. 設定（場所と日時）
# ---------------------------------------------
point = (34.2325, 135.1917) # 和歌山駅
dist = 300 # エリアを少し狭めます（計算を軽くするため）

# ★ここで日時を自由に設定できます（今は夏の日中を想定）
target_date = datetime(2024, 8, 1, 5, 0, 0, tzinfo=timezone.utc)

# ---------------------------------------------
# 2. データ取得・加工
# ---------------------------------------------
print("データを取得中...")
# 道路データの取得
G = ox.graph_from_point(point, dist=dist, network_type='walk')

# 建物データの取得
tags = {'building': True}
buildings = ox.features_from_point(point, tags=tags, dist=dist)

# ★重要：高さデータ(NaN)を「10メートル」で埋める処理
# height列がない場合も考慮して作成
if 'height' not in buildings.columns:
    buildings['height'] = 10.0
else:
    # データがあっても数値に変換できないものやNaNを10.0にする
    buildings['height'] = pd.to_numeric(buildings['height'], errors='coerce').fillna(10.0)

# 座標系をメートル単位（平面直角座標系）に変換（計算しやすくするため）
buildings_proj = buildings.to_crs(epsg=6676) # 日本の平面座標系の一つ

# ---------------------------------------------
# 3. 太陽位置の計算
# ---------------------------------------------
lat, lon = point
altitude = get_altitude(lat, lon, target_date) # 太陽の高度（角度）
azimuth = get_azimuth(lat, lon, target_date)   # 太陽の方位（北=0度）

print(f"日時: {target_date}")
print(f"太陽高度: {altitude:.2f}度")
print(f"太陽方位: {azimuth:.2f}度")

# 夜なら影の計算をしない
if altitude <= 0:
    print("夜なので影はありません。")
    shadows = gpd.GeoDataFrame()
else:
    # ---------------------------------------------
    # 4. 影の生成ロジック（ここがキモです！）
    # ---------------------------------------------
    shadow_polygons = []
    
    # 影の長さを計算係数 (高さ1mあたりの影の長さ)
    # L = h / tan(altitude)
    shadow_len_factor = 1 / math.tan(math.radians(altitude))
    
    # 影が伸びる方向（X, Y成分）
    # 数学的な方位角の調整（北=0, 時計回り）から、三角関数の角度へ
    azimuth_math = math.radians(azimuth - 180) 
    dx_factor = shadow_len_factor * math.sin(azimuth_math)
    dy_factor = shadow_len_factor * math.cos(azimuth_math)

    print("影データを生成中...")
    
    for idx, row in buildings_proj.iterrows():
        h = row['height']
        geom = row['geometry']
        
        # 建物がPolygon（多角形）の場合のみ処理
        if geom.geom_type == 'Polygon':
            # 建物の頂点を取得
            x, y = geom.exterior.coords.xy
            new_coords = []
            
            # 各頂点をずらして、影の形を作る（簡易的な手法）
            # 本来は「建物の形」と「ずらした形」の凸包を取るのが正確ですが、
            # ここではシンプルに「屋根をずらして地面に投影した形」を作ります
            points_ground = list(zip(x, y))
            points_roof_shadow = [(xi + h * dx_factor, yi + h * dy_factor) for xi, yi in zip(x, y)]
            
            # 地面の点と、影の先の点を合わせて大きな多角形を作る
            # (shapelyのconvex_hullを使って、点群を包む最小の多角形＝影を作る)
            from shapely.geometry import MultiPoint
            all_points = points_ground + points_roof_shadow
            shadow_poly = MultiPoint(all_points).convex_hull
            
            shadow_polygons.append(shadow_poly)

    # 影データをGeoDataFrameにまとめる
    shadows = gpd.GeoDataFrame(geometry=shadow_polygons, crs=buildings_proj.crs)

# ---------------------------------------------
# 5. 可視化
# ---------------------------------------------
# 元の座標系(緯度経度)に戻す
if not shadows.empty:
    shadows = shadows.to_crs(epsg=4326)

fig, ax = ox.plot_graph(G, show=False, close=False, edge_color='#cccccc', node_size=0)

# 影を描画（黒、半透明）
if not shadows.empty:
    shadows.plot(ax=ax, facecolor='black', alpha=0.5, zorder=2)

# 建物を描画（オレンジ）
buildings.plot(ax=ax, facecolor='orange', alpha=1.0, zorder=3)

plt.title(f"Shadow Map: {target_date.strftime('%Y-%m-%d %H:%M')}")
plt.show()