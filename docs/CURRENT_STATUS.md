# KAGE-MICHI Current Status

最終更新: 2026-08-10

このファイルは、新しいチャットや作業者が短時間で現在地を把握するための引き継ぎ資料です。作業状況が変わるたびに短く上書きします。

## 現在のPhase

Phase 1「基準計測と再現環境」は完了しました。開発TODOは4/17件完了（24%）です。Phase 2「処理分割とオフライン化」をIssue駆動で開始しました。

## 現在のブランチ

- ブランチ: `agent/issue-3-package-structure`
- 状態: Issue #3の実装・検証完了。GitHubでレビュー・統合する段階
- 基準ブランチ: `main`
- 最新マージ済みPR: [#2 P0の性能計測基盤を整備](https://github.com/momo27182/KAGE-MICHI/pull/2)
- 現在のIssue: [#3 新規パッケージ構成を作る](https://github.com/momo27182/KAGE-MICHI/issues/3)
- 次のIssue: [#4 OSM取得とローカル読込を分離する](https://github.com/momo27182/KAGE-MICHI/issues/4)

## 今回完了したこと

- Issue #3で製品コードを7つの責務へ分離する最小構成を作成した
- `docs/architecture.md`へ責務、依存方向、段階移植手順を記録した
- import、循環依存、境界差し替えを検証する構成テスト3件を追加した
- 基準ケース5件を `benchmarks/cases.json` に固定した
- Python 3.12.13と直接依存11件を固定し、再現用環境を構築した
- 現行版を区間別に計測できるベンチマークCLIを実装した
- 初回実行とキャッシュ後実行を計測し、ボトルネックを特定した
- 性能基準レポート、テスト5件、性能計測JSON出力を追加した
- NotionのPhase 1タスク4件を完了へ更新した

## ブロッカー

なし。

## 次に行う3項目

1. Issue #3の変更をコミットして作業ブランチをプッシュする
2. `Closes #3`を含むPull Requestを作成して確認する
3. PR #3相当のマージ後、Issue #4のブランチを作る

## 現時点の重要な判断

- 利用者の検索時にはOSMを取得せず、道路・建物・地点データを事前生成する
- 投影済みの中間成果物を保存し、起動時の復元処理も短縮する
- 影計算と経路探索を独立させ、時刻変更時は必要な処理だけを再実行する
- ハッカソン版は原本として直接変更せず、新規実装は `src/` に作る
- GitHubの `log.md`、Notion、本文書を役割分担して更新する

## 重要な測定値

- 初回実行: 約225秒（データ取得・整形219.62秒、影2.29秒）
- キャッシュ後: 6.12秒（データ復元3.22秒、影2.29秒、経路0.18秒、地図0.44秒）
- 経路探索単体: 約0.002秒。現時点では最適化対象ではない
- キャッシュ後の地図HTML: 約1.59MB
- テスト: 8件成功

## 参照先

- [GitHub](https://github.com/momo27182/KAGE-MICHI)
- [Notion KAGEMICHI](https://app.notion.com/p/3b7e0745b52580fcaa44d4d3d8ff52ff)
- [実装方針・ロードマップ](https://app.notion.com/p/3b7e0745b5258106a707ca84078bbad6)
- [開発TODO](https://app.notion.com/p/b9292d3f66bb41a0897720b6648bc91f)
- [進捗記録](https://app.notion.com/p/3b7e0745b525815b99b0ce64d1a1239b)

## 新しいチャットへの依頼文

> KAGE-MICHIの開発を続けます。最初に `AGENT.md`、`docs/CURRENT_STATUS.md`、Notionの最新進捗と進行中TODOを確認してください。現在地を要約してから、次の未完了作業へ進んでください。
