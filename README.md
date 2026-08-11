# KAGE-MICHI

時間帯ごとの日陰と暑熱リスクを考慮し、「最短」ではなく「最涼」の徒歩ルートを提案するプロジェクトです。

## フォルダ構成

```text
.
├─ archive/
│  └─ hackathon_2025/  # ハッカソン時点のコード・資料・動画・生成物
├─ src/                 # これから開発する製品コード
├─ tests/               # 自動テストと検証コード
├─ docs/                # 設計、調査、データ出典、評価結果
│  ├─ CURRENT_STATUS.md # 新しいチャット向けの短い引き継ぎ
│  └─ decisions/        # 重要な技術判断と理由
├─ data/                # 開発用データの置き場所
├─ AGENT.md             # 開発方針と作業ルール
└─ log.md               # 日付順の判断・作業・検証記録
```

過去の成果物は比較・再現のために保存し、原則として直接編集しません。新しい実装は `src/`、新しいテストは `tests/` に作成します。

作業を始めるときは、先に `AGENT.md` と `docs/CURRENT_STATUS.md` を確認してください。詳細な過去履歴が必要な場合だけ `log.md` を参照します。

## GitHubでの開発

- リモート: `https://github.com/momo27182/KAGE-MICHI.git`
- 基準ブランチ: `main`
- 開発ブランチの命名例: `agent/p0-performance-foundation`

新しい変更は目的ごとのブランチで行い、確認後にPull Requestで`main`へ統合します。大容量動画、取得キャッシュ、PLATEAU等の原本データ、秘密情報はGitへ直接追加しません。

## 開発環境

検証済みPythonは3.12.13です。PowerShellでは次の手順で環境を作ります。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

基準ケースは`benchmarks/cases.json`、性能計測の結果要約は`docs/performance-baseline.md`で管理します。

OSMデータはアプリ実行時に取得せず、事前に加工済み成果物を作成します。

```powershell
.\.venv\Scripts\python.exe scripts\prepare_osm_data.py
```

生成物は`data/prepared/`へ保存され、Git管理対象外です。形式と出典の詳細は`data/README.md`、設計判断は`docs/decisions/0002-store-prepared-osm-as-graphml-and-geopackage.md`を参照してください。

影計算と経路探索はUIから独立して実行・計測できます。

```powershell
.\.venv\Scripts\python.exe scripts\measure_shadow_routing.py
```

計算の入出力、現在の簡易モデル、既知の制約は`docs/shadow-routing.md`に記録しています。

## 軽量Streamlit画面

事前生成済みデータがある状態で、次のコマンドから新しい画面を起動できます。

```powershell
.\.venv\Scripts\python.exe -m streamlit run src\streamlit_app.py
```

同じ日時・地点の再表示ではデータ、影、経路のキャッシュを再利用します。再計算範囲と実測値は`docs/lightweight-ui.md`を参照してください。
