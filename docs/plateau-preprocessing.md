# PLATEAU建物前処理

更新日: 2026-09-24

## 目的

約940MBのCityGMLをアプリ実行時に解析せず、和歌山駅周辺の建物だけを軽量なGeoPackageへ事前変換する。取得元、CRS、件数、欠損、チェックサム、処理性能は`manifest.json`で追跡する。

## 実行方法

CityGML ZIPを`data/raw/plateau/30201_wakayama-shi_2023/`に置き、リポジトリルートで実行する。原本と生成物はGit対象外である。

```powershell
.\.venv\Scripts\python.exe scripts\prepare_plateau_buildings.py `
  data\raw\plateau\30201_wakayama-shi_2023\30201_wakayama-shi_city_2023_citygml_2_op.zip `
  --output data\prepared\plateau\wakayama-station `
  --source-etag c15ded3d34ee50b1c22b1bde668dfc93 `
  --source-acquired-at-utc 2026-09-24T02:43:38+00:00
```

初期値は基準点`34.2325, 135.1917`、半径1,700m、投影先`EPSG:6676`。同名成果物がある場合は停止し、意図した再生成だけ`--overwrite`を付ける。中央1メッシュの試験は`--mesh 51352175 --radius-m 100`で実行できる。

## 入出力と判定

- `udx/bldg/*_bldg_*.gml`だけをXMLストリームで読む。
- GMLの`srsName`を検証し、実データの`EPSG:6697`から`EPSG:6676`へ変換する。
- LOD1立体の底面とZの上下差を保存する。`measuredHeight`と`lod1HeightType`も保存し、高さ不明を10mなどで補完しない。
- 同一`gml:id`は1件に正規化し、最後に半径1.7kmの円と交差する建物だけ残す。
- `buildings.gpkg`と`manifest.json`を出力する。読込時はファイルと意味内容のSHA-256、CRSを再検証する。

## 2026-09-24実データ検証

| 範囲 | CityGML | 建物 | 高さ欠損 | LOD2あり | 時間 | ピークメモリ | 出力 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `51352175`、100m | 1 | 19 | 0 | 1 | 62.32秒 | 123.6MiB | 104KiB |
| 半径1.7km、16メッシュ | 16 | 23,032 | 0 | 2 | 2,645.83秒 | 165.5MiB | 7.22MiB |

半径1.7kmの意味チェックサムは`a603482554e3b90806d333544cd03bda7e9adb0bd952cde6e640b93a327a6bc2`。入力ZIPは939,693,415 bytes、SHA-256は`dcc552ff1e3706ec774e478846b1e230856501c850bb59f970817be8148ba184`。

初回変換は開発者向けバッチであり、通常のアプリ起動時間には含まれない。一方、44分は長いため、再生成を頻繁に行う場合はメッシュ単位の中間キャッシュと再開機能を次の性能改善候補とする。
