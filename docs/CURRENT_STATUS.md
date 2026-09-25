# KAGE-MICHI Current Status

最終更新: 2026-09-25

## 現在のPhase・GitHub

Phase 4「道路日陰率の改善」を進行中。Issue #33の画面統合を専用ブランチで実装中。

- ブランチ: `codex/issue-33-integrate-precomputed-shade`（`origin/main`の`efe5715`から作成）。
- [PR #30](https://github.com/momo27182/KAGE-MICHI/pull/30)はReady化・squash merge済み。
- [Issue #29](https://github.com/momo27182/KAGE-MICHI/issues/29)は自動クローズ。
- [PR #32](https://github.com/momo27182/KAGE-MICHI/pull/32)はReady化・squash merge済み。
- [Issue #31](https://github.com/momo27182/KAGE-MICHI/issues/31)は自動クローズ。Notion TODOは完了・完了条件確認済み。
- NPZ + JSON manifest、原子的公開、誤上書き防止、改ざん・入力版不一致検出、夜間の意味を実装済み。
- 実データ24時間・288時刻の生成に成功。45分02秒、ピーク447.1 MiB、出力1.06 MiB、完全読込最大0.0787秒。
- マージコミットは`efe5715`。マージ後の記録だけローカル未コミットで次作業へ引き継ぐ。
- [Issue #33](https://github.com/momo27182/KAGE-MICHI/issues/33)「事前計算済み日陰率を経路探索・画面へ統合する」を実装中。Notion TODOは進行中。
- [Draft PR #34](https://github.com/momo27182/KAGE-MICHI/pull/34)を`Closes #33`付きで作成。実装は1コミットに集約済み。
- 直前5分への時刻解決、安定エッジキー完全照合、部分日陰率による経路比較、成果物キャッシュ、欠損・不一致の明示エラー、昼夜表示を実装。
- 実データ測定は初回0.788秒、時刻変更0.089秒、地点変更0.205秒。全72テスト成功。
- NotionでIssue #27・#29・#31と重複していた旧TODO 3件を、対応Issueを記載して完了へ整理。全体22/28件、Phase 4は4/6件完了。

## Issue #29の結果

- 部分日陰を0〜100%で評価し、日向距離と経路コストへ連続的に反映する実装を追加。
- 和歌山駅周辺10,262エッジ・PLATEAU影・2026-08-11 14:00 JSTで比較。
- 平均絶対誤差 / 道路判定時間: 中央点 0.070651 / 0.126秒、5m 0.009395 / 1.364秒、10m 0.016072 / 0.783秒、交差長 0 / 67.468秒。
- 5mサンプリングを次の事前計算方式として採用。1時刻のfloat32値は0.039 MiB、5分刻み24時間は11.274 MiB。
- 全62テスト成功。詳細は `docs/edge-shade-comparison.md` とADR 0003。

## ブロッカー・次の3項目

ブロッカーなし。通常ユーザーで起動済みの旧Streamlitは成果物の所有権により読み取り拒否となったが、成果物を生成した実行環境で検証用サーバーを起動し、実ブラウザー確認まで完了した。WindowsのACL・所有権変更は成功しておらず、永続変更は発生していない。

1. PR #34の差分とGitHub状態を最終レビューする。
2. 問題がなければReady化・squash mergeする。
3. main同期後、Issue #33・Notion TODO・Phase 4完了条件を確認する。

## 維持する判断

- 交差長は比較基準であり現地の正解値ではない。通常経路探索には使わない。
- 画面の既定経路はPLATEAU由来・5mサンプリングの事前計算済み道路日陰率を使う。
- 夜間の`shade_ratio=1.0`は建物日陰ではなく直達日射なしを意味し、`daylight=false`と組で扱う。
- 事前計算成果物はNPZ + JSON manifestとし、日付・地域・入力版・影モデル版を追跡する。
- PLATEAU原本・加工済み巨大データ・一時ベンチマーク出力はGitへ含めない。
- 影モデルは地形、樹木、庇、複雑な屋根、建物間遮蔽を扱わない。
