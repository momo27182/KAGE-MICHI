# src

今後の製品コードを置くフォルダです。

影計算、経路探索、データ取得、暑熱評価、UIを分離し、ハッカソン版のような単一ファイルの派生を増やさない方針です。製品モジュールの責務と依存方向は[`docs/architecture.md`](../docs/architecture.md)で管理します。

現在は`kage_michi`パッケージに、基準ケースの検証と区間別性能計測の共通機能を置いています。外部依存を必要としないため、再現環境を整える前でもテストできます。

製品コードは`models`、`data`、`shadows`、`routing`、`heat`、`application`、`presentation`へ分けています。これらの境界は標準ライブラリだけでimportでき、OSMnx、GeoPandas、Streamlitなどの具体実装は後続Issueで追加します。

