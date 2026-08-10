# KAGE-MICHI アーキテクチャ

最終更新: 2026-08-10

## 目的

ハッカソン版の単一ファイルを直接変更せず、機能ごとに段階移植できる依存方向を定める。現段階では実装を細かく分けすぎず、責務の境界だけを固定する。

## モジュールの責務

| モジュール | 責務 | 主な依存先 |
|---|---|---|
| `models` | 座標、入力条件、経路、暑熱評価などの共通型 | なし |
| `data` | 道路・建物・地点データを供給する境界 | `models` |
| `shadows` | 日時と空間データから影を計算する境界 | `models`, `data` |
| `routing` | 空間データと影から徒歩経路を探索する境界 | `models`, `data`, `shadows` |
| `heat` | 気象条件と経路から暑熱リスクを評価する境界 | `models` |
| `application` | 各境界を呼び出し、1回のルート計画処理を組み立てる | 上記すべて |
| `presentation` | 結果をUIへ渡す表示用データへ変換する | `models` |

具体的な外部接続とファイル永続化は`infrastructure/`へ置く。`infrastructure/osm_prepared.py`だけがOSM取得とOSMnx形式を知り、製品側は`SpatialDataSource`境界を通じて利用する。

`benchmark_cases`、`performance`、`legacy_benchmark`は移行期間中の計測支援であり、製品の依存方向には含めない。

## 依存ルール

```text
presentation ────────────────┐
                             v
application -> data ------> models
            -> shadows ----> models
            -> routing ----> models
            -> heat -------> models
```

- `models`は他の製品モジュールをimportしない
- `data`、`shadows`、`routing`、`heat`は`application`や`presentation`をimportしない
- `application`は処理を組み立てるが、OSMnxやStreamlitなどの具体実装を直接生成しない
- `presentation`は計算を行わず、UI固有ライブラリもこの段階では読み込まない
- 外部サービスやファイル形式はProtocolの実装として後から追加する

## 段階移植

1. Issue #3で共通型、境界Protocol、処理の組み立てを用意する
2. Issue #4で`SpatialDataSource`のOSM取得実装とローカル読込実装を分ける。道路はGraphML、建物・地点はGeoPackage、追跡情報はJSON manifestとして保存する
3. 影計算と経路探索をそれぞれのProtocol実装として移植する
4. 最後にStreamlit UIを`presentation`と`application`へ接続する

## 対象外

この構成だけでは、PLATEAU、高さ推定、道路区間の日陰率、気象API、Streamlit画面は実装しない。それぞれ個別Issueで完了条件と性能・精度の測定方法を定める。
