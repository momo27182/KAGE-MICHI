# KAGE-MICHI Current Status

最終更新: 2026-09-23

## 現在のPhase・GitHub

Phase 2後半は完了。Phase 3「PLATEAU小範囲検証」の最初の調査をローカルで完了した。

- ブランチ: `codex/issue-23-plateau-research`（`origin/main`の`cee2924`から作成）。
- [Issue #23](https://github.com/momo27182/KAGE-MICHI/issues/23)「PLATEAUデータと利用条件を調査する」は進行中。[Draft PR #24](https://github.com/momo27182/KAGE-MICHI/pull/24)を作成済み。
- [PR #16](https://github.com/momo27182/KAGE-MICHI/pull/16)はReady化・squash merge済み。[Issue #15](https://github.com/momo27182/KAGE-MICHI/issues/15)は自動クローズ。
- [PR #18](https://github.com/momo27182/KAGE-MICHI/pull/18)はReady化・squash merge済み。mainコミット`dffb817`。[Issue #17](https://github.com/momo27182/KAGE-MICHI/issues/17)は自動クローズ。
- [PR #20](https://github.com/momo27182/KAGE-MICHI/pull/20)はReady化・squash merge済み。mainコミット`c7a2dcd`。[Issue #19](https://github.com/momo27182/KAGE-MICHI/issues/19)は自動クローズ。
- [PR #22](https://github.com/momo27182/KAGE-MICHI/pull/22)はReady化・squash merge済み。mainコミット`cee2924`。[Issue #21](https://github.com/momo27182/KAGE-MICHI/issues/21)は自動クローズ。
- マージ後の記録変更は未コミットで保持し、次の作業ブランチへ引き継ぐ。

## Issue #23の調査結果

- 和歌山市2023年度CityGML（v4、標準製品仕様書4.1、建築物LOD1・LOD2）を公式データセットとして採用する。
- 公式CityGML ZIPは939,693,415 bytes。HTTP 200、Range対応、ETagを確認したが、原本は未取得・Git対象外。
- 和歌山駅の3次メッシュ候補は`51352175`。半径1.7kmは隣接メッシュも含め、索引図とGML Envelopeで確定する。
- 利用条件、出典表示、CRS・高さの扱い、取得更新方針、次の前処理入出力を`docs/plateau-data-research.md`へ記録した。

## 残る制約・次の3項目

1. PR #24の差分とGitHub状態を確認する。
2. 問題がなければReady化・squash mergeする。
3. マージ後、「PLATEAU建物の前処理パイプラインを作る」をIssue化する。

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

> AGENT.md、docs/CURRENT_STATUS.md、Notion最新進捗を読んでください。Issue #23の変更はDraft PR #24へプッシュ済みです。差分とGitHub状態を確認し、問題がなければReady化・squash mergeしてください。
