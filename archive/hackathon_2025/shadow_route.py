import osmnx as ox
import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
import networkx as nx
from shapely.geometry import MultiPoint, LineString, Point
from pysolar.solar import get_altitude, get_azimuth
from datetime import datetime, timezone
import math

# ---------------------------------------------
# 1. 設定
# ---------------------------------------------
point = (34.2325, 135.1917) # 和歌山駅
dist = 400  # エリア半径

# 日時（2024年8月1日 14:00 JST -> UTC 05:00）
target_date = datetime(2024, 8, 1, 5, 0, 0, tzinfo=timezone.utc)

# ---------------------------------------------
# 2. データ取得・前処理
# ---------------------------------------------
print("1/4: 地図データを取得中...")
# 道路（network_type='walk'で歩道優先）
G = ox.graph_from_point(point, dist=dist, network_type='walk')
# 建物
tags = {'building': True}
buildings = ox.features_from_point(point, tags=tags, dist=dist)

# 高さ補完
if 'height' not in buildings.columns:
    buildings['height'] = 10.0
else:
    buildings['height'] = pd.to_numeric(buildings['height'], errors='coerce').fillna(10.0)

# 座標系変換（メートル単位へ）
buildings_proj = buildings.to_crs(epsg=6676)
G_proj = ox.project_graph(G, to_crs='epsg:6676')

# ---------------------------------------------
# 3. 影の生成（前回のコードと同じ）
# ---------------------------------------------
print("2/4: 影を計算中...")
lat, lon = point
altitude = get_altitude(lat, lon, target_date)
azimuth = get_azimuth(lat, lon, target_date)

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

# 影を1つの大きな図形に統合（重なり判定を高速化するため）
from shapely.ops import unary_union
if shadow_polygons:
    all_shadows = unary_union(shadow_polygons)
else:
    all_shadows = None

# ---------------------------------------------
# 4. ルート探索の準備（ここが新機能！）
# ---------------------------------------------
print("3/4: 道の「日陰コスト」を計算中...")

# 日向の道のペナルティ（高いほど日陰を優先します）
SUN_PENALTY = 10.0 

# 全ての道（エッジ）をチェックして、影に入っているか調べる
for u, v, k, data in G_proj.edges(keys=True, data=True):
    # 道の長さ（メートル）
    length = data['length']
    
    # 道の形状（Geometry）を取得。なければ直線を引く
    if 'geometry' in data:
        edge_geom = data['geometry']
    else:
        # ノード座標から直線を生成
        p1 = G_proj.nodes[u]
        p2 = G_proj.nodes[v]
        edge_geom = LineString([(p1['x'], p1['y']), (p2['x'], p2['y'])])
    
    # 影と重なっているか判定
    is_shaded = False
    if all_shadows and all_shadows.intersects(edge_geom):
        # 完全に重なってなくても、少しかすっていれば「日陰あり」とみなす簡易判定
        is_shaded = True
    
    # コストの設定
    if is_shaded:
        data['shadow_cost'] = length          # 日陰なら、距離そのまま
        data['color'] = '#3366ff'             # 青色（デバッグ用）
    else:
        data['shadow_cost'] = length * SUN_PENALTY # 日向なら、距離10倍
        data['color'] = '#ff3333'             # 赤色

# ---------------------------------------------
# 5. ルート検索実行
# ---------------------------------------------
print("4/4: ルート検索中...")

# スタートとゴールを適当に決めます（地図の端から端へ）
# ノードリストをX座標でソートして、東端と西端を取得
nodes = list(G_proj.nodes(data=True))
sorted_nodes = sorted(nodes, key=lambda n: n[1]['x'])
orig_node = sorted_nodes[0][0]  # 一番西の点
dest_node = sorted_nodes[-1][0] # 一番東の点

# A: 通常の最短ルート（距離優先）
route_shortest = nx.shortest_path(G_proj, orig_node, dest_node, weight='length')

# B: 日陰優先ルート（shadow_cost優先）
route_shadow = nx.shortest_path(G_proj, orig_node, dest_node, weight='shadow_cost')

print("完了！描画します。")

# ---------------------------------------------
# 6. 結果の可視化
# ---------------------------------------------
fig, ax = plt.subplots(figsize=(10, 10), facecolor='black')

# 背景色
ax.set_facecolor('black')

# 1. 影を描画
if shadow_polygons:
    gpd.GeoSeries([all_shadows]).plot(ax=ax, facecolor='gray', alpha=0.5, zorder=1)

# 2. 建物を描画
buildings_proj.plot(ax=ax, facecolor='orange', alpha=0.8, zorder=2)

# 3. 道路網を描画（薄く）
# ox.plot_graph の代わりに簡易描画
for u, v, data in G_proj.edges(data=True):
    c = '#444444' # 暗いグレー
    if 'geometry' in data:
        xs, ys = data['geometry'].xy
        ax.plot(xs, ys, c=c, linewidth=0.5, zorder=0)

# 4. ルート描画
# 通常ルート（赤点線）
path_geom_short = [
    (G_proj.nodes[n]['x'], G_proj.nodes[n]['y']) for n in route_shortest
]
px, py = zip(*path_geom_short)
ax.plot(px, py, color='red', linewidth=4, linestyle=':', label='Shortest', zorder=4)

# 日陰ルート（青実線）
path_geom_shadow = [
    (G_proj.nodes[n]['x'], G_proj.nodes[n]['y']) for n in route_shadow
]
sx, sy = zip(*path_geom_shadow)
ax.plot(sx, sy, color='#00ccff', linewidth=3, alpha=0.9, label='Shadow Route', zorder=5)

# スタート・ゴール
ax.scatter(px[0], py[0], c='lime', s=100, zorder=6, label='Start')
ax.scatter(px[-1], py[-1], c='red', s=100, zorder=6, label='Goal')

import folium

# ---------------------------------------------
# 7. HTML地図として保存（Folium）
# ---------------------------------------------
print("地図(HTML)を作成中...")

# 地図の中心座標
m = folium.Map(location=[lat, lon], zoom_start=17, tiles='CartoDB dark_matter')

# 1. 影を描画（黒いポリゴン）
if shadow_polygons:
    # 座標系を緯度経度に戻す
    shadows_gdf = gpd.GeoDataFrame(geometry=[all_shadows], crs=buildings_proj.crs).to_crs(epsg=4326)
    folium.GeoJson(
        shadows_gdf,
        style_function=lambda x: {'fillColor': 'black', 'color': 'none', 'fillOpacity': 0.6}
    ).add_to(m)

# 2. 建物を描画（オレンジ）
buildings_geo = buildings.reset_index() # インデックスをリセット
folium.GeoJson(
    buildings_geo,
    style_function=lambda x: {'fillColor': 'orange', 'color': 'orange', 'weight': 1, 'fillOpacity': 0.8},
    tooltip=folium.GeoJsonTooltip(fields=['height'], aliases=['高さ:']) # マウスオーバーで高さを表示
    # ※ height列がない場合はエラーになるので、その場合は tooltip行を削除してください
).add_to(m)

# 3. ルート描画
# 最短ルート（赤）
route_line_short = LineString([(G.nodes[n]['y'], G.nodes[n]['x']) for n in route_shortest])
folium.PolyLine(
    locations=[(y, x) for x, y in route_line_short.coords],
    color="red", weight=4, opacity=0.7, dash_array='5, 10', tooltip="最短ルート"
).add_to(m)

# 日陰ルート（青）
route_line_shadow = LineString([(G.nodes[n]['y'], G.nodes[n]['x']) for n in route_shadow])
folium.PolyLine(
    locations=[(y, x) for x, y in route_line_shadow.coords],
    color="#33ccff", weight=5, opacity=0.9, tooltip="日陰ルート"
).add_to(m)

# スタートとゴール
folium.Marker([route_line_short.coords[0][1], route_line_short.coords[0][0]], popup="Start", icon=folium.Icon(color='green')).add_to(m)
folium.Marker([route_line_short.coords[-1][1], route_line_short.coords[-1][0]], popup="Goal", icon=folium.Icon(color='red')).add_to(m)

# 保存
m.save("shadow_map.html")
print("完了！ 'shadow_map.html' というファイルができました。ブラウザで開いてみてください。")