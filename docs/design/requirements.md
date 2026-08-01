(requirements)=
# 要件

## 目的

ゲームの真実を決定的なdomainで管理し、HTTP、画面、LLM、永続化を交換可能な境界から
接続する。公開状態とprivate stateを分離し、外部LLMを使わずに主要機能と品質を
再現できることを必須とする。

## 利用者

| 利用者 | 要求 |
| --- | --- |
| ゲーム参加者 | ゲームを作成し、観測可能な情報から合法な行動を提出する |
| 観戦者 | 公開状態と解決済みtimelineを参照する |
| 管理者 | 運用診断を安全な要約で行い、必要な場合だけ専用境界から完全状態を確認する |
| 開発者 | 同じseedと入力から結果を再現し、境界違反を自動検出する |
| 実験者 | Rule Pack、Agent、条件、seedを固定し、反復結果を比較・再生成する |
| 組み込み利用者 | 外部serviceを起動せず、Python APIから一局または反復実験を実行する |
| 運用者 | 設定検証、migration、起動、health確認、品質判定を自動化された入口から行う |

## 機能要件

| ID | 要件 | 主な境界 |
| --- | --- | --- |
| `REQ-GAME-001` | 完全なv2 setup documentからゲームを作成・復元・replayできる | domain、application |
| `REQ-GAME-008` | ルール、任意IDの役職、能力component、世界観、用語、ナレーション、プレイヤー生成規則を一体の設定として編集できる | setup、clients |
| `REQ-GAME-009` | 背景固有の名称を画面とLLMへ反映し、mechanicsの安定IDと分離する | projection、agents |
| `REQ-GAME-010` | setup、mechanics、生成rosterのchecksumを保存し、replayとLLM traceで追跡できる | persistence、LLM |
| `REQ-GAME-011` | 自動プレイヤーが公開根拠に基づいて合法な行動と対象を選び、発言・投票・役職行動へ一貫して反映する | agents、gameplayレビュー |
| `REQ-GAME-012` | 同じsetupとseedから同じプレイヤー、役職割当、ゲーム進行を生成し、用途別seedを相互に分離する | setup、application、domain |
| `REQ-GAME-013` | プレイヤー previewは公開personaだけを返し、役職とprivate strategyを返さない | API、clients |
| `REQ-GAME-014` | 昼の議論は全員のopeningを解決まで秘匿して同時公開し、その発言を参照するresponseを順番に公開する。この組を設定回数だけ反復し、既定値は1回とする | setup、domain、agents、clients |
| `REQ-LLM-001` | Fakeと実LLMが同じchat request、応答検証、fallbackを通り、意思決定ごとの呼び出しを最大1回にする | アダプター contract、trace |
| `REQ-LLM-002` | quick、standard、deepで参照履歴と出力上限を切り替え、ゲーム作成時の選択を保存する | API、worker、clients、persistence |
| `REQ-GAME-002` | 行動受付、phase進行、勝敗、可視性をdomainが判定する | domain |
| `REQ-GAME-003` | factionと勝利陣営は`village`、`werewolf`、`fox`の正規IDで表す | domain、application |
| `REQ-API-001` | CLIとStreamlitは同じHTTP契約でゲームを操作する | API |
| `REQ-API-002` | 各clientは公開operationを分類し、対象となる利用者機能へ到達できる | API、clients |
| `REQ-RUNTIME-001` | 外部依存の障害時もプロセスのshellと安全な診断を返し、影響する機能だけを停止する | API、clients |
| `REQ-RULE-001` | 8種類の能力componentを組み合わせ、単一のrule factoryで実行規則を構築する | application、domain |
| `REQ-RULE-002` | 人数、役職、能力、開始phase、投票、公開範囲、第1夜の能力有効性を設定だけで変更できる | setup、domain |
| `REQ-RULE-003` | 設定で表せない新しい意味論は、明示登録した外部Rule Packから副作用のないPolicyとして注入できる | domain、composition root |
| `REQ-AGENT-001` | agentは観測可能な情報と合法候補だけから判断する | agents |
| `REQ-AGENT-002` | provider非依存の契約を実装した外部Agentを、製品コードの変更なしにプレイヤー単位で注入できる | agents、simulation |
| `REQ-SDK-001` | 標準インストールだけでsetup、domain、Agent契約、一局実行、反復実験を利用できる | package |
| `REQ-SIM-001` | Notebook、worker、実験が同じ一局実行器を使い、step単位で停止、再開、観測できる | simulation |
| `REQ-EXP-001` | Rule PackとAgentの条件を分離し、paired seedと割当rotationで再現可能に比較できる | experiments |
| `REQ-EXP-002` | trial成果物から評価値とreportを再生成し、中断再開しても同じtrialを重複実行しない | experiments |
| `REQ-APP-001` | applicationをstateless facadeとして、in-memoryまたは外部リポジトリとexecutorを注入して利用できる | application |
| `REQ-DATA-001` | acceptedコマンド、event、state、projectionから完全replayできる | persistence |
| `REQ-DATA-002` | replayはコマンドを先頭から再実行し、各versionのstate、event、projectionを照合する | application |
| `REQ-DATA-003` | 本人のsetupを不変revisionとして保存し、保存競合を検出し、他利用者と匿名利用者から隔離する | application、Supabase |
| `REQ-ADMIN-001` | 管理者はprivate payloadを返さず整合性と処理状態を診断できる | admin API |
| `REQ-ADMIN-002` | 完全状態のrevealは設定で有効化した管理者専用APIだけが返す | admin API |

## 品質要件

| ID | 要件 | 受入方法 |
| --- | --- | --- |
| `REQ-QUALITY-001` | 同じseed、定義、入力列から同じ状態とevent列を得る | unit、monkey |
| `REQ-QUALITY-002` | 失敗した状態遷移でstateを変更しない | domain unit |
| `REQ-SECURITY-001` | public response、timeline、ログへprivate情報を出さない | unit、integration |
| `REQ-ARCH-001` | layer依存、公開面、循環を機械検査できる | architecture |
| `REQ-OPS-001` | リポジトリ内の検証と運用準備をCLIから再現できる | quality、リリース |
| `REQ-QUALITY-003` | 実行せずにテスト結果、画面、設定、ログを成果物一式からレビューできる | manifest、レビュー |
| `REQ-QUALITY-004` | 品質実行が依存環境と所有外resourceを変更しない | fingerprint、lease |
| `REQ-QUALITY-005` | 組み込み実装と外部実装へ同じcontractテストを適用できる | rule、agent、リポジトリ |
| `REQ-QUALITY-006` | 実験結果の状態と製品品質の判定を別の成果物と語彙で記録する | experiments、quality |
| `REQ-DOCS-001` | 設計書と公開Python APIをwarningなしで生成し、モジュールとobjectのHTML構造を検査できる | docs build、HTML検査 |

## 1.0.0提供範囲

- 一つのmanualプレイヤーと自動プレイヤーを含むゲーム進行
- 同梱TOMLから構築する標準6人ゲームと、任意IDの役職・能力componentによるcustom setup
- FakeListChatModelによるoffline実行
- Supabase Auth、PostgreSQL永続化、operation queue
- FastAPI、CLI、Streamlit、worker
- replay、private LLM trace、管理診断
- Python標準ライブラリだけで動作するHeadless SDK
- 明示登録する外部Rule Packと外部Agent
- 再現可能な一局実行と反復実験
- localとCIで共有する品質プロファイル

production deployment、DB backup、外部監視、secret rotationは利用するplatformが
所有する。リポジトリは接続契約、health、ログ、migration、検証入口を提供する。
複数manualプレイヤー、任意code実行を伴う能力DSL、設定からのimport、自動plugin探索、
信頼できないpluginのsandbox実行、分散実験、実験管理Web dashboard、外部frontendの実装は
1.0.0に含めない。0.xのsetup、replay、保存データ、Python APIとの後方互換は維持しない。
