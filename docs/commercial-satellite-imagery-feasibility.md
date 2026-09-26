# 商用高解像度衛星画像による影検証の実現性

調査日: 2026-11-06

## 結論

無料衛星画像は道路日陰率の定量検証には粗すぎるが、商用高解像度衛星画像は条件付きで利用できる可能性がある。Planet Select（SkyFi提供）の既存画像カタログで、和歌山駅中心34.2325, 135.1917を含む25km²を検索し、既存画像81件を確認した。

購入候補になり得るSkySat画像も確認できたが、既存画像は最低25km²の注文条件があり、表示単価6米ドル/km²から最低150米ドルとなる。購入・アカウント作成・問い合わせは行っていない。

## 確認した既存画像

### 第一候補

- 画像ID: `PLANET:20250919_053612_ssc9_u0001`
- 撮影日時: 2025-09-19 14:36 JST
- GSD: 72cm
- 推定雲量: 0%
- オフナディア角: 17.70度
- バンド数: 4
- 納品形式: GeoTIFF
- カタログ上のAOI交差面積: 6.75km²
- 表示単価: 6米ドル/km²
- 最低注文面積: 25km²
- 表示上の最低費用: 150米ドル

午後の建物影を確認でき、雲量0%である点は有望。ただし、72cm/画素では幅2mの歩道は約3画素、幅6mの道路は約8画素であり、縁石単位の精密な正解値ではなく、広い道路区間の日陰率を概略評価する用途が現実的である。

### その他の有望例

| 撮影日時（JST） | GSD | 雲量 | オフナディア角 | AOI交差面積 |
| --- | ---: | ---: | ---: | ---: |
| 2025-08-03 07:58 | 72cm | 0% | 17.20度 | 4.59km² |
| 2025-07-31 08:07 | 70cm | 9% | 14.10度 | 12.86km² |
| 2025-07-15 14:25 | 74cm | 1% | 17.40度 | 20.45km² |
| 2025-06-30 08:52 | 63cm | 0% | 16.70度 | 0.61km² |
| 2025-06-28 08:53 | 64cm | 0% | 16.90度 | 1.40km² |

カタログの低解像度プレビューでは撮影ストリップとAOIの重なりを確認できるが、道路の影境界を購入前に定量判読できる解像度ではない。

## 新規撮影の費用目安

Planetの公式案内では、SkySatのセルフサービス撮影は次の価格が示されている。

- Flexible Tasking: 12米ドル/km²、最低25km²または300米ドル
- Assured Tasking: 40米ドル/km²、最低25km²なら1,000米ドル

Flexibleは7日以上の撮影期間を指定し、雲量15%未満を目標に条件のよい機会を選ぶ。Assuredは特定日時を優先できるが、天候は保証されない。影検証では太陽位置と撮影時刻が重要なためAssuredが要件に近いが、初期検証には高額である。

## 使用する場合の条件

1. 画像フットプリントがWV-01〜WV-04または評価対象道路を覆う。
2. 雲量5%以下を目安とし、対象区間に雲・雲影がない。
3. オフナディア角20度未満、可能なら15度以下を優先する。
4. 撮影日時を分単位で取得し、KAGE-MICHIの同一日時の日陰率を生成する。
5. 建物更新時期がPLATEAU 2023年度データと大きく矛盾しないか確認する。
6. 購入前に、研究・開発解析、派生成果、スクリーンショット公開、保存期間のライセンス条件を確認する。
7. 道路全体を手作業または画像分類でマスクし、衛星画像の位置ずれ・画素境界を不確かさとして報告する。

## 推奨判断

現時点では購入しない。まず第一候補と2025-07-15画像について、販売元へ次を確認する。

- 和歌山駅周辺の必要道路を覆う25km²注文範囲を指定できるか
- 研究・卒業制作・オープンソース開発での解析と派生統計公開が可能か
- 購入前に対象道路の判読可能性を確認できる拡大プレビューを提供できるか
- 学術・教育向け割引または試用データがあるか

現地撮影12観測は無料で同一地点・同一時刻を設計できるため、Issue #41の主経路として維持する。衛星画像は、現地観測後に誤差原因を広域確認する補助データ、または費用を許容できる場合の比較データとする。

## 公式資料

- [Planet SkySat](https://docs.planet.com/data/imagery/skysat/)
- [Planet SkySatSceneメタデータ](https://docs.planet.com/data/imagery/skysat/item-types/skysatscene/)
- [Planet Search and Preview Imagery](https://docs.planet.com/platform/get-started/access-data/search-and-preview/)
- [Planet Single Order Tasking](https://www.planet.com/pulse/agile-eo-webinar-fast-flexible-tasking/)
- [Planet Tasking注文条件](https://docs.planet.com/platform/get-started/access-data/task-imagery/create_orders/)
- [Airbus Pléiades Neo](https://space-solutions.airbus.com/imagery/our-optical-and-radar-satellite-imagery/pleiades-neo/)
- [ESA Sentinel-2](https://www.esa.int/Applications/Observing_the_Earth/Copernicus/Sentinel-2/Facts_and_figures)
- [USGS Landsat 8](https://www.usgs.gov/landsat-missions/landsat-8)

価格・カタログ件数・提供条件は調査時点の表示であり、購入前に再確認する。
