# KAGE-MICHI Current Status

最終更新: 2026-09-25

## 現在のPhase・GitHub

Phase 4「道路日陰率の改善」を進行中。Issue #31の事前生成・保存を実装中。

- ブランチ: `codex/issue-31-precomputed-shade`（基点は`main`の`60ee3b3`）。
- [PR #30](https://github.com/momo27182/KAGE-MICHI/pull/30)はReady化・squash merge済み。
- [Issue #29](https://github.com/momo27182/KAGE-MICHI/issues/29)は自動クローズ。
- [Issue #31](https://github.com/momo27182/KAGE-MICHI/issues/31)「5分刻みの道路日陰率を事前生成・保存する」に着手。Notion TODOは進行中。
- NPZ + JSON manifest、原子的公開、誤上書き防止、改ざん・入力版不一致検出、夜間の意味を実装済み。
- 実データ24時間・288時刻の生成に成功。45分02秒、ピーク447.1 MiB、出力1.06 MiB、完全読込最大0.0787秒。
- 実装・テスト・記録を1コミットへまとめてプッシュし、[Draft PR #32](https://github.com/momo27182/KAGE-MICHI/pull/32)を作成。本文に`Closes #31`を記載。

## Issue #29の結果

- 部分日陰を0〜100%で評価し、日向距離と経路コストへ連続的に反映する実装を追加。
- 和歌山駅周辺10,262エッジ・PLATEAU影・2026-08-11 14:00 JSTで比較。
- 平均絶対誤差 / 道路判定時間: 中央点 0.070651 / 0.126秒、5m 0.009395 / 1.364秒、10m 0.016072 / 0.783秒、交差長 0 / 67.468秒。
- 5mサンプリングを次の事前計算方式として採用。1時刻のfloat32値は0.039 MiB、5分刻み24時間は11.274 MiB。
- 全62テスト成功。詳細は `docs/edge-shade-comparison.md` とADR 0003。

## ブロッカー・次の3項目

ブロッカーなし。

1. Draft PR #32の差分とGitHub状態を最終レビューする。
2. 問題がなければReady化・squash mergeする。
3. マージ後にNotionの状態と完了条件確認を完了へ変更する。

## 維持する判断

- 交差長は比較基準であり現地の正解値ではない。通常経路探索には使わない。
- 画面の既定経路はまだ中央点方式のまま。事前計算・保存・検証後に切り替える。
- 夜間の`shade_ratio=1.0`は建物日陰ではなく直達日射なしを意味し、`daylight=false`と組で扱う。
- 事前計算成果物はNPZ + JSON manifestとし、日付・地域・入力版・影モデル版を追跡する。
- PLATEAU原本・加工済み巨大データ・一時ベンチマーク出力はGitへ含めない。
- 影モデルは地形、樹木、庇、複雑な屋根、建物間遮蔽を扱わない。
