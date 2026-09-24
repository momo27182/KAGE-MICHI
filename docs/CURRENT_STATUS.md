# KAGE-MICHI Current Status

最終更新: 2026-09-24

## 現在のPhase・GitHub

Phase 3「PLATEAU小範囲検証」の[Issue #25](https://github.com/momo27182/KAGE-MICHI/issues/25)を実装済み。[Draft PR #26](https://github.com/momo27182/KAGE-MICHI/pull/26)でレビュー待ち。

- ブランチ: `codex/issue-25-plateau-preprocessing`
- 実装コミット: `9c8f481`。PR本文に`Closes #25`を記載。
- CityGML前処理、検証付きローカル読込、CLI、自動テスト、運用手順を追加。
- 約940MBの原本と生成GeoPackageはGit対象外。アプリ実行時に外部取得やCityGML解析を行わない。

## Issue #25の検証結果

- 1メッシュ: 19棟、高さ欠損0、LOD2あり1、62.32秒、ピーク123.6MiB、出力104KiB。
- 半径1.7km・16メッシュ: 23,032棟、高さ欠損0、LOD2あり2、2,645.83秒、ピーク165.5MiB、出力7.22MiB。
- 入力CRS `EPSG:6697`を検証し、`EPSG:6676`へ変換。高さはLOD1のZ差で、10m固定補完は行わない。
- データ詳細・実行手順: `docs/plateau-preprocessing.md`

## ブロッカー・次の3項目

ブロッカーなし。

1. PR #26の差分・GitHub状態を最終レビューする。
2. 問題がなければReady化・squash mergeする。
3. マージ後、Notion TODOを完了へ変更し、次のPLATEAU比較タスクをIssue化する。

## 維持する判断

- PLATEAU前処理は開発者向けオフラインバッチ。通常実行はチェックサム検証済みGeoPackageだけを読む。
- 44分の全域再生成は重い。頻繁な更新が必要になれば、メッシュ単位の中間キャッシュと再開機能を追加する。
- Phase 2のOSM画面はまだPLATEAUを使わない。次にOSM建物とPLATEAU LOD1の精度・影・性能を比較してから統合する。
- 高さ欠損10m、凸包影、道路中央点判定は現行OSM実装の制約として残る。
