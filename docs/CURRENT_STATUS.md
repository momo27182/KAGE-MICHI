# KAGE-MICHI Current Status

最終更新: 2026-09-22

## 現在のPhase・GitHub

Phase 2後半「UI機能の段階統合」。Issue #19のコンビニ・給水地点表示を実装・検証中。

- ブランチ: `codex/issue-19-local-spots`。基準はmainの`dffb817`。前回の未コミット記録を保持して着手。
- [PR #16](https://github.com/momo27182/KAGE-MICHI/pull/16)はReady化・squash merge済み。[Issue #15](https://github.com/momo27182/KAGE-MICHI/issues/15)は自動クローズ。
- [PR #18](https://github.com/momo27182/KAGE-MICHI/pull/18)はReady化・squash merge済み。mainコミット`dffb817`。[Issue #17](https://github.com/momo27182/KAGE-MICHI/issues/17)は自動クローズ。
- [Issue #19](https://github.com/momo27182/KAGE-MICHI/issues/19)を作成し、Notion TODOを進行中へ更新。
- 記録更新はこの作業ブランチで管理し、mainへ直接プッシュしない。

## Issue #19の成果・確認

- 加工済み`spots.gpkg`からコンビニ・給水地点を分類し、Point/Polygonを代表点へ変換して地図表示。
- サイドバーに種別ごとの表示切替、本文に件数・出典・取得処理日時・利用上の制約を表示。
- 現データはコンビニ39件、給水地点0件。`amenity`列自体がないケースを正常な0件として扱う。
- 施設表示専用の軽量読込を追加し、道路グラフ・建物・影計算・経路探索を呼ばない。
- 全43テスト、構文確認、差分チェック成功。実ブラウザーで39件表示と表示切替を確認。

## 未確認・次の3項目

ユーザー承認のもとCodex sandbox状態を修復し、実ブラウザー検証を再開。全境界操作、視点保持、経路保持・失効を確認。視点復帰不具合と確定ピンのクリック遮断を修正。灰色背景は地図iframe再作成時のタイル再取得が原因で、確定時は再作成しないよう改善。最終クリック応答5回は883〜1,148ms、中央値972ms。取消時のタイル再表示5回は中央値458ms、最大3,124ms。確定時は535msでタイル9枚を維持し灰色背景なし。全40テスト、構文確認、差分チェック成功。詳細はdocs/map-selection.md。

1. Issue #19の記録とNotion TODOを完了状態へ更新する。
2. ユーザー依頼後にコミット・プッシュし、`Closes #19`付きPull Requestを作成する。
3. PR差分をレビュー後、問題がなければReady化・squash mergeする。

ブラウザー操作は復旧済み。一時フォルダの読み取り対象がCodexSandboxUsersへ広がるリスクはユーザーへ説明済みで、書き込み権限は付与していない。基本動作確認やDOM表示時間は、網羅的な実画面検証や描画時間の代用ではない。

## 測定値・維持する判断

- AppTestサーバー再実行0.0845〜0.1019秒、中央値0.0986秒（5回）。重い関数呼出し0。ブラウザーの応答時間ではない。
- 過去: ローカル読込0.76〜1.15秒、影2.687秒、経路0.239秒。
- 過去の軽量画面: 初回5.723秒、キャッシュ後0.007秒、地点変更0.389秒。
- archiveは変更しない。OSM取得はオフライン前処理。
- 高さ欠損10m・凸包影・道路中央点判定は今回変更していない。
- 暑熱情報は公的情報源と更新時刻を伴うPhase 5で設計。
- 地名検索の明示操作・キャッシュ・Nominatim利用条件を維持。
- 最短経路比較はPhase 2、別時刻比較はPhase 4。主要駅の検索補正は暫定策。

## 参照先・再開用依頼文

- [検証TODO](https://app.notion.com/p/3d0e0745b52581ce8511e683b3ad22b2)
- [進捗記録](https://app.notion.com/p/3b7e0745b525815b99b0ce64d1a1239b)

> AGENT.md、docs/CURRENT_STATUS.md、Notion最新進捗を読んでください。Issue #19の施設表示はローカル実装・検証済みです。次はユーザー依頼に応じてコミット・プッシュし、Closes #19付きPRを作成してください。
