import osmnx as ox
import matplotlib.pyplot as plt

# 1. 場所の指定（和歌山駅の座標）
# 緯度: 34.2325, 経度: 135.1917
point = (34.2325, 135.1917)
dist = 500  # 半径500メートル

print("データをダウンロード中...（数秒〜数分かかります）")

# 2. 道路ネットワークの取得（歩き 'walk' モード）
G = ox.graph_from_point(point, dist=dist, network_type='walk')

# 3. 建物の取得
# 'building'タグがついているものを全て取得します
tags = {'building': True}
buildings = ox.features_from_point(point, tags=tags, dist=dist)

print(f"取得完了: 建物数 {len(buildings)} 件")

# 4. データの確認（高さ情報があるかチェック）
# 多くの建物は高さ(height)が入っていないことが多いので、その確認です
if 'height' in buildings.columns:
    print("--- 高さ情報のサンプル ---")
    print(buildings['height'].head())
else:
    print("警告: このエリアのデータには'height'（高さ）列が含まれていません。")

# 5. 可視化（プロット）
fig, ax = ox.plot_graph(G, show=False, close=False, edge_color='#999999', node_size=0)
buildings.plot(ax=ax, facecolor='orange', alpha=0.7)

plt.title("Wakayama Station Area")
plt.show()