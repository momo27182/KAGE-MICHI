# 和歌山市PLATEAUデータ調査

調査日: 2026-09-23

対象: 和歌山駅周辺（基準点 34.2325, 135.1917、現行検証範囲は半径1.7km）

## 結論

小範囲検証には、G空間情報センターの「3D都市モデル（Project PLATEAU）和歌山市（2023年度）」の **CityGML（v4）** を使用する。

- データセットID: `plateau-30201-wakayama-shi-2023`
- 都市コード: `30201`
- 準拠仕様: 3D都市モデル標準製品仕様書 第4.1版
- 建築物: LOD1、LOD2
- 配布ページ: https://www.geospatial.jp/ckan/dataset/plateau-30201-wakayama-shi-2023
- CityGML: https://assets.cms.plateau.reearth.io/assets/33/e43850-ce18-4bcb-9a8b-88bf2eb8f2a3/30201_wakayama-shi_city_2023_citygml_2_op.zip
- 索引図: https://assets.cms.plateau.reearth.io/assets/31/3825e6-0fd9-4afe-8c3e-17aa3037ea89/30201_indexmap_op.pdf

2026-09-23のHEAD確認では、CityGML ZIPはHTTP 200、`application/zip`、939,693,415 bytes（約896 MiB）、Range取得対応、ETag `c15ded3d34ee50b1c22b1bde668dfc93` だった。巨大な原本はGitへ追加しない。

## データ仕様

公式CKANメタデータは2023年度データの最新版をV4とし、建築物LOD1・LOD2をCityGMLと3D Tilesで提供している。建築物以外にも道路、都市計画、土地利用、災害リスク、地形等が含まれるが、最初の検証では `udx/bldg/` だけを入力にする。

国交省の整備状況資料では、和歌山市の建築物LOD1は市全域を対象として令和4年度に整備され、令和5年度に建物構造・地上階数・津波避難施設等の属性が追加されている。作成時点の原典に基づくため、現況と一致する保証はない。

### 座標参照系

PLATEAU標準仕様の基本は、日本測地系2011の経緯度と東京湾平均海面を基準とする標高の複合座標参照系（例: EPSG:6697、`JGD2011,TP/(B,L),H`）である。ただし推測で固定せず、各GMLの `gml:Envelope/@srsName` を検証する。元CRS、単位、変換先CRS、変換ライブラリの版をmanifestへ残す。

### 建築物形状と高さ

- LOD1は一律高さの立体。標準作業手順では、上面高さに建物平面内の点群の中央値を使うことが原則。
- `bldg:measuredHeight` は地上の最低点から最高点までの計測高さで、LOD1の押し出し高さと一致しない場合がある。
- `uro:lod1HeightType` はLOD1上面高さの根拠を示す。
- LOD2は屋根面・外壁面等を区別できるが、整備範囲はLOD1より限定され得る。

最初の影比較ではLOD1立体の底面・上面Z差を第一候補とし、`measuredHeight` と `lod1HeightType` も保存する。高さ属性だけで立体を再生成する方式は比較用とし、元のLOD1幾何を正本にする。

## 和歌山駅周辺の切り出し

建築物ファイルは原則3次メッシュ単位で分割される。基準点から計算した3次メッシュ候補は `51352175`。ただし半径1.7kmには中央メッシュだけでは不足するため、次の順で対象を決める。

1. 索引図またはZIP内ファイル名から、半径1.7kmの外接矩形に交差する3次メッシュを列挙する。
2. 各GMLのEnvelopeと外接矩形の交差を確認する。
3. 建築物を最終的な円形範囲で空間フィルタする。
4. 境界をまたぐ建築物の欠落を防ぐため、隣接メッシュも入力候補に含める。

`51352175` は開始候補であり、実データの索引図・Envelope確認を完了条件とする。

## 利用条件

PLATEAU Site Policyでは、G空間情報センターの3D都市モデルの著作権は各地方公共団体に帰属し、特記がなければ公共データ利用規約（PDL1.0）に準拠する。CC BY 4.0と互換性があり、ODC BYまたはODbLでの利用も妨げない。公式CKANも同ポリシーをライセンスとしている。

本プロジェクトではCC BY 4.0互換の表示条件として、画面・README・加工データmanifestへ次を記載する。

> 出典：和歌山市「3D都市モデル（Project PLATEAU）和歌山市（2023年度）」、国土交通省Project PLATEAU / G空間情報センター（URL）、KAGE-MICHIで加工

加工物を国土交通省または和歌山市が作成したように見せず、取得日、年度、URL、加工内容を併記する。公開・再配布前には同梱README、拡張製品仕様書、原典資料リストと測量法上の扱いを再確認する。

## 取得・更新・追跡方針

- 原本: `data/raw/plateau/30201_wakayama-shi_2023/`（Git対象外）
- 加工物: `data/prepared/plateau/wakayama-station/`（Git対象外）
- コードと小さなmanifestだけをGit管理する
- 公式CKAN APIから最新リソースURLを解決し、配布URLを永久固定しない
- データセットID、CKAN `metadata_modified`、URL、Content-Length、ETag、取得日時、SHA-256を記録する
- 同名成果物を上書きせず、年度・版をmanifestで識別する

調査時のCKAN `metadata_modified` は `2026-04-13T04:20:52.732537`。前処理実行時にメタデータを再取得する。

## 次の前処理Issueへ渡す仕様

入力は公式データセットID、CityGML ZIPまたは `udx/bldg/*.gml`、基準点、半径、対象LOD。出力は建物ID、2D外形、LOD、底面・上面標高、高さ、`measuredHeight`、高さ根拠を持つGeoPackageまたはParquetと、出典・版・CRS変換・件数・欠損率・チェックサムを持つmanifestとする。

必須検証:

- GMLのCRSを検証してから変換する
- XML名前空間やファイル順に依存しない
- 範囲境界の建物を欠落・重複させない
- 高さ欠損を10mへ置換せず欠損として集計する
- 同じ入力から同じ件数・形状・manifestを再現できる
- 1メッシュでメモリ、時間、建物数を測定してから半径1.7kmへ広げる

## 未解決事項

- 和歌山駅周辺にLOD2建築物が含まれるか。
- 実GMLの `srsName`、Z値、建築物ID・高さ属性の充足率。
- 約940MBのZIP全体取得とRange利用のどちらを採るか。
- 加工データを再配布する場合の測量成果の複製・使用承認の要否。

## 一次情報

- 国土交通省オープンデータ: https://www.mlit.go.jp/plateau/open-data/
- G空間情報センター 和歌山市: https://www.geospatial.jp/ckan/dataset/plateau-30201-wakayama-shi-2023
- 公式CKAN API: https://www.geospatial.jp/ckan/api/3/action/package_show?id=plateau-30201-wakayama-shi-2023
- PLATEAU Site Policy: https://www.mlit.go.jp/plateau/site-policy/
- 標準製品仕様書: https://www.mlit.go.jp/plateaudocument/
- 入手方法とファイル構成: https://www.mlit.go.jp/plateau/learning/tpc03-1/
- 和歌山市の整備状況: https://www.mlit.go.jp/toshi/daisei/content/001884717.pdf
