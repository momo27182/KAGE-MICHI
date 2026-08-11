# KAGE-MICHI Current Status

最終更新: 2026-08-11

## 現在のPhase

Phase 2「処理分割とオフライン化」を進めています。開発TODOは6/17件完了（35%）で、Issue #7を実装中です。

## 現在のブランチ

- ブランチ: `agent/issue-7-shadow-routing`
- 状態: Issue #7のDraft PR #8を作成し、レビュー待ち
- 基準ブランチ: `main`
- 最新マージ済みPR: [#6 OSM取得とローカル読込を分離](https://github.com/momo27182/KAGE-MICHI/pull/6)
- 現在のIssue: [#7 影計算と経路探索を分離してテストする](https://github.com/momo27182/KAGE-MICHI/issues/7)
- 現在のPR: [#8 影計算と経路探索を分離してテストする](https://github.com/momo27182/KAGE-MICHI/pull/8)

## 今回完了したこと

- 影計算を`BuildingShadowCalculator`、経路探索を`MidpointShadeRoutePlanner`としてUIから分離した
- 太陽位置を差し替え可能にし、固定入力で影結果を再現できるようにした
- 夜間、高さ欠損10m補完、経路なし、固定入力の再現テストを追加した
- 実データで影計算2.687秒、経路探索0.239秒を個別計測した
- 現行の凸包影、中央点判定、固定倍率などの制約を文書化した

## ブロッカー

なし。

## 次に行う3項目

1. PR #8の差分とGitHub上の状態を確認する
2. 問題がなければReady for reviewに変更する
3. 最終確認後にPR #8をマージし、Issue #7を閉じる

## 重要な測定値

- 加工済みOSMローカル読込: 0.76〜1.15秒
- 影計算: 2.687秒（7,870建物、7,865影ポリゴン）
- 経路探索: 0.239秒（21ノード、1,294.543m、中央点判定の日陰率30.366%）
- 自動テスト: 20件成功

## 現時点の重要な判断

- 利用者の検索時にはOSMを取得せず、加工済みデータをローカルから読む
- 影計算と経路探索を独立させ、時刻変更時に必要な処理だけ再実行できる境界を保つ
- 現行精度（高さ欠損10m、凸包影、道路中央点判定）は維持し、精度改善は別Issueで比較可能にする
- ハッカソン版は原本として直接変更しない

## 参照先

- [GitHub](https://github.com/momo27182/KAGE-MICHI)
- [影計算と経路探索](shadow-routing.md)
- [Notion KAGEMICHI](https://app.notion.com/p/3b7e0745b52580fcaa44d4d3d8ff52ff)
- [開発TODO](https://app.notion.com/p/b9292d3f66bb41a0897720b6648bc91f)
- [進捗記録](https://app.notion.com/p/3b7e0745b525815b99b0ce64d1a1239b)

## 新しいチャットへの依頼文

> KAGE-MICHIの開発を続けます。最初に`AGENT.md`、`docs/CURRENT_STATUS.md`、Notionの最新進捗と進行中TODOを確認してください。Draft PR #8を確認し、問題がなければマージへ進んでください。
