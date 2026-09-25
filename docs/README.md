# docs

設計、調査結果、データ出典、ライセンス、精度評価、実測結果を置くフォルダです。

日々の短い作業履歴はルートの `log.md` に残し、長くなる調査や設計はこのフォルダに分離して `log.md` から参照します。

- `CURRENT_STATUS.md`: 最新状態だけを短くまとめる引き継ぎ資料。作業状況が変わるたびに上書きする。
- `architecture.md`: 製品モジュールの責務、依存方向、段階移植の設計。
- `plateau-data-research.md`: 和歌山市PLATEAUデータ、利用条件、取得・前処理方針の調査。
- `edge-shade-comparison.md`: 道路日陰率の中央点・5m・10m・交差長方式の精度と性能比較。
- `edge-shade-comparison.json`: 固定条件で再現した道路日陰率比較の小さな結果スナップショット。
- `precomputed-shade.md`: 5分刻み道路日陰率の生成、保存、検証、夜間の意味、実測結果。
- `precomputed-shade-benchmark.json`: 固定日24時間・288時刻の小さな実測スナップショット。
- `time-comparison.md`: 基準日時と比較日時の4経路表示、エラー方針、キャッシュ、実測結果。
- `weather-heat-source-selection.md`: 公式の気象・暑熱情報源比較、採用方針、データ契約、安全表示、障害時方針。
- `weather-data-integration.md`: 公式WBGT・警戒情報の取得、20分キャッシュ、期限・障害状態、手動疎通確認。
- `decisions/`: 後から変更コストが高い技術判断と理由をADRとして保存する。

