# data

開発・検証用データを置くフォルダです。

PLATEAUや気象データを追加するときは、入手元、取得日、対象地域、ライセンス、加工内容を `docs/` に記録します。巨大な原本データや秘密情報を無条件にバージョン管理へ含めないでください。

## OSMの加工済みデータ

`scripts/prepare_osm_data.py`は、OSMデータを取得・投影して`data/prepared/<地域名>/`へ保存します。この生成物はGit管理対象外です。

- `walk.graphml`: 投影済み歩行者道路グラフ
- `buildings.gpkg`: 投影済み建物
- `spots.gpkg`: 投影済みコンビニ・給水地点
- `manifest.json`: 出典、取得処理日時、中心点、半径、座標系、件数、ファイル名、各ファイルのSHA-256。OSMnxのHTTPキャッシュ利用時は、元レスポンスが取得処理日時より古い可能性も記録する

実行例:

```powershell
.\.venv\Scripts\python.exe scripts\prepare_osm_data.py
```

同名の成果物がある場合は誤上書きを防ぐため停止します。意図して更新するときだけ`--overwrite`を指定します。OpenStreetMapデータを表示・配布する場合は、`© OpenStreetMap contributors`と[著作権・ライセンス情報](https://www.openstreetmap.org/copyright)を表示してください。

