# KAGE-MICHI Current Status

最終更新: 2026-09-22

## 現在のPhase・GitHub

Phase 2後半「UI機能の段階統合」。Issue #17の実ブラウザー検証・応答実測・発見不具合の修正はローカルで完了。PR統合待ち。

- ブランチ: `codex/issue-17-browser-validation`。基準はmainの`7261b15`。前回の未コミット記録を保持して着手。
- [PR #16](https://github.com/momo27182/KAGE-MICHI/pull/16)はReady化・squash merge済み。[Issue #15](https://github.com/momo27182/KAGE-MICHI/issues/15)は自動クローズ。
- [Issue #17](https://github.com/momo27182/KAGE-MICHI/issues/17)のローカル作業を完了し、[Draft PR #18](https://github.com/momo27182/KAGE-MICHI/pull/18)を作成済み。本文に`Closes #17`を記載。
- Notion: Issue #17の検証TODOはローカル完了。GitHub統合前のため進行中として管理。
- 記録更新はこの作業ブランチで管理し、mainへ直接プッシュしない。

## 今回の成果・確認

- 初期地図、仮候補、明示反映、取消・再選択、範囲外/同一点チェックを統合。
- 地図操作と重い計算を分離し、座標/マーカー同期、結果保持・条件変更時の非表示を実装。
- ユーザーによる実画面の基本動作確認あり。
- マージ後も全40テスト成功、構文確認成功。マージ前の差分レビュー・差分チェック成功。
- 設計・残る検証手順: [map-selection.md](map-selection.md)

## 未確認・次の3項目

ユーザー承認のもとCodex sandbox状態を修復し、実ブラウザー検証を再開。全境界操作、視点保持、経路保持・失効を確認。視点復帰不具合と確定ピンのクリック遮断を修正。灰色背景は地図iframe再作成時のタイル再取得が原因で、確定時は再作成しないよう改善。最終クリック応答5回は883〜1,148ms、中央値972ms。取消時のタイル再表示5回は中央値458ms、最大3,124ms。確定時は535msでタイル9枚を維持し灰色背景なし。全40テスト、構文確認、差分チェック成功。詳細はdocs/map-selection.md。

1. PR #18の差分とGitHub状態を確認する。
2. 問題がなければReady化・squash mergeする。
3. 次のIssueとしてコンビニ・給水地点表示へ進む。

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

> AGENT.md、docs/CURRENT_STATUS.md、docs/map-selection.md、Notion最新進捗を読んでください。Issue #17の変更はDraft PR #18へプッシュ済みです。差分とGitHub状態を確認し、問題がなければReady化・squash mergeしてください。
