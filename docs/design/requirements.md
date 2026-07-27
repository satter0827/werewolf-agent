(requirements)=
# 要件

## 目的

ゲームの真実を決定的な domain で管理し、HTTP、画面、LLM、永続化を交換可能な境界から
接続する。公開状態と private state を分離し、外部 LLM を使わずに主要機能と品質を
再現できることを必須とする。

## 利用者

| 利用者 | 要求 |
| --- | --- |
| ゲーム参加者 | ゲームを作成し、観測可能な情報から合法な行動を提出する |
| 観戦者 | 公開状態と解決済み timeline を参照する |
| 管理者 | 運用診断を安全な要約で行い、必要な場合だけ専用境界から完全状態を確認する |
| 開発者 | 同じ seed と入力から結果を再現し、境界違反を自動検出する |
| 運用者 | 設定検証、migration、起動、health 確認、品質判定を自動化された入口から行う |

## 機能要件

| ID | 要件 | 主な境界 |
| --- | --- | --- |
| `REQ-GAME-001` | 完全なsetup documentからゲームを作成・復元できる | domain |
| `REQ-GAME-008` | ルール、役職、能力、背景、登場人物を一体の設定として編集できる | setup、clients |
| `REQ-GAME-009` | 背景固有の名称を画面とLLMへ反映し、mechanicsの安定IDと分離する | projection、agents |
| `REQ-GAME-010` | setupとmechanicsのchecksumを保存し、replayとLLM traceで追跡できる | persistence、LLM |
| `REQ-GAME-002` | 行動受付、phase 進行、勝敗、可視性を domain が判定する | domain |
| `REQ-GAME-003` | factionと勝利陣営は`village`、`werewolf`、`fox`の正規IDで表す | domain、application |
| `REQ-API-001` | CLIとStreamlitは同じHTTP契約でゲームを操作する | API |
| `REQ-API-002` | 各clientは公開operationを分類し、対象となる利用者機能へ到達できる | API、clients |
| `REQ-RUNTIME-001` | 外部依存の障害時もprocessのshellと安全な診断を返し、影響する機能だけを停止する | API、clients |
| `REQ-RULE-001` | 登録済みrule policyの構成を選択し、gameとreplay snapshotへ保存できる | application、domain |
| `REQ-AGENT-001` | agent は観測可能な情報と合法候補だけから判断する | agents |
| `REQ-DATA-001` | accepted command、event、state、projection から完全 replay できる | persistence |
| `REQ-DATA-002` | replayはcommandを先頭から再実行し、各versionのstate、event、projectionを照合する | application |
| `REQ-ADMIN-001` | 管理者は private payload を返さず整合性と処理状態を診断できる | admin API |
| `REQ-ADMIN-002` | 完全状態の reveal は設定で有効化した管理者専用 API だけが返す | admin API |

## 品質要件

| ID | 要件 | 受入方法 |
| --- | --- | --- |
| `REQ-QUALITY-001` | 同じ seed、定義、入力列から同じ状態と event 列を得る | unit、monkey |
| `REQ-QUALITY-002` | 失敗した状態遷移で state を変更しない | domain unit |
| `REQ-SECURITY-001` | public response、timeline、log へ private 情報を出さない | unit、integration |
| `REQ-ARCH-001` | layer 依存、公開面、循環を機械検査できる | architecture |
| `REQ-OPS-001` | repository 内の検証と運用準備を CLI から再現できる | quality、release |
| `REQ-QUALITY-003` | 実行せずにtest結果、画面、設定、logを成果物一式からレビューできる | manifest、review |
| `REQ-QUALITY-004` | 品質実行が依存環境と所有外resourceを変更しない | fingerprint、lease |
| `REQ-DOCS-001` | 設計書と公開 API を warning なしで自動生成できる | docs build |

## 提供範囲

- 一つの manual player と自動 player を含むゲーム進行
- `villager`、`werewolf`、`seer`、`knight`、`medium`、`apothecary`、`hunter`、`madman`、`fox`の9役職
- FakeListLLM による offline 実行
- Supabase Auth、PostgreSQL 永続化、operation queue
- FastAPI、CLI、Streamlit、worker
- replay、private LLM trace、管理診断
- local と CI で共有する品質 profile

production deployment、DB backup、外部監視、secret rotation は利用する platform が
所有する。repository は接続契約、health、log、migration、検証入口を提供する。
複数manual player、任意code実行を伴う能力DSL、plugin機構は現行要件に含めない。
