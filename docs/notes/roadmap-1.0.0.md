(roadmap-1-0-0)=
# 1.0.0ロードマップ

## 目的

1.0.0は、設定可能な人狼ルールと外部Agentを同じ決定的な実行器で動かし、
再現可能な条件で比較・分析できるヘッドレス実験SDKを提供する。
API、worker、CLI、Streamlitは同じSDKを利用する提供層として接続する。

標準インストールは、domain、setup、Agent契約、Simulation、Experimentを含む。
このHeadless SDKはPython標準ライブラリだけで動作し、application、LLM、API、Streamlit、
worker、Supabaseに必要な第三者パッケージはextraへ分離する。

## 設計原則

- `Game`だけがゲーム状態を変更する。
- setup、Rule、Agent、Simulation、Experimentの公開契約を責務別モジュールへ分ける。
- 可変値は設定へ置き、新しい意味論だけを明示的に注入する。
- 外部Rule Packと外部AgentはPythonオブジェクトとして明示登録し、自動探索しない。
- 設定からPythonのimport pathや任意コードを読み込まない。
- 組み込み実装と外部実装は同じcontractテストを通る。
- Notebook、レビュー、workerは同じSimulation step APIを使う。
- 実験結果と品質判定を分離する。
- 後方互換用のalias、旧schema読替え、暗黙fallbackを残さない。
- 各段階は利用可能な縦断経路を完成させてから次へ進む。

## 目標構造

| 公開モジュール | 責務 | 標準インストール |
| --- | --- | --- |
| `werewolf_agent.domain` | Game、state、event、Rule Policy、replay | 対象 |
| `werewolf_agent.setup` | setup定義、検証、プレイヤー生成、seed、checksum | 対象 |
| `werewolf_agent.agents` | provider非依存のAgent契約 | 対象 |
| `werewolf_agent.simulation` | 一局のヘッドレス実行 | 対象 |
| `werewolf_agent.experiments` | 反復、評価、比較、成果物 | 対象 |
| `werewolf_agent.application` | stateless use case、認可、リポジトリport | extra |
| `werewolf_agent.adapters` | Supabase、HTTP、LLM、外部I/O | extra |
| `werewolf_agent.api`、`worker`、`clients` | serviceと利用者interface | extra |

パッケージrootは`__version__`だけを公開する。利用者は責務を所有するモジュールから型と関数を
importする。console scriptはoptional依存を遅延importし、不足時は必要なextraを案内する。

## 到達段階

### 1. 要件と現行動作を固定する

1.0.0の利用者、公開面、対象外を要件へ追加する。実装済み境界の依存方向を構造規則で確認し、
setup、Rule、Agent、Simulation、Experimentの新しい公開境界は実装と同じ変更で追加する。

標準ゲームのstate、event順序、visibility、replay checksumをcharacterizationテストで固定する。
第1夜の占い、投票、狐、immunity、vulnerability、death reactionを代表ケースにする。
完全なJSON全体ではなく、意味的に安定させる値だけを検査する。

完了条件は、後続の構造変更が既存のゲーム結果または秘匿境界を変えた場合に、
対象テストが失敗することである。

### 2. Headless SDKのパッケージ境界を作る

パッケージrootのdomain再公開を削除し、責務別モジュールを公開面とする。
標準runtime dependenciesを空にし、application、API、CLI、LLM、Streamlit、workerの
依存をextraへ移す。

`GameSetupDocument`、プレイヤー生成、seed namespace、checksum、Rule Definition変換を
`werewolf_agent.setup`へ移す。setup modelと意味検証はimmutableな標準ライブラリ型で表し、
Pydanticはapplication入力とHTTP wire schemaに限定する。

完了条件は、clean環境の標準インストールでHeadless SDKをimportでき、同じsetupとseedから
同じrosterとRule Definitionを生成できることである。

### 3. Rule Policyを外部注入可能にする

domainは`CompiledRuleSet`、`RulePackProvider`、`RulePackManifest`、
`RulePolicyRegistry`、`AbilityPolicy`、`VotingPolicy`、`VictoryPolicy`を公開する。
Policyは状態を変更せず、用途別Outcomeを返す。DomainがOutcomeを検証し、状態とeventへ
一括適用する。

現在の能力、投票、勝敗を`CoreRulePack`へ移す。外部Rule Packは自動探索せず、
利用者またはcomposition rootがProviderを明示登録する。manifestにはcontract version、
implementation version、fingerprintを含める。

第1夜に占いだけを行うルールは、開始phaseと各能力の`enabled_first_night`で表現する。
この要件のために新しいphaseまたは初期化hookを追加しない。

完了条件は、本体を変更せずに外部Rule Packを登録でき、Coreと外部実装が同じcontractテスト、
決定性、rollback、replay、visibility検査を通ることである。

### 4. Agent SDKを外部注入可能にする

agentsは`AgentFactory`、`AgentSession`、`AgentContext`、`DecisionRequest`、
`DecisionResponse`、`AgentSpec`、`DecisionTrace`を公開する。
契約は同期処理を基本とし、timeoutとcancelはSimulationまたはアダプターが管理する。

Agentには本人用observation、public timeline、合法action、合法target、deadline、decision seedだけを
渡す。domainの完全state、`GameView`、`Action`、リポジトリ、application serviceは渡さない。
belief、confidence、intent、diagnostic metadataは任意とし、chain-of-thoughtは要求または保存しない。

Fake、random legal、heuristic、fault、LangChainを同じSession契約へ移す。
完了条件は、本体を変更せずに外部Agentを注入でき、game、trial、プレイヤー間の状態分離、
秘匿性、timeout、cancel、closeをcontractテストで確認できることである。

### 5. ゲーム進行をSimulationへ統一する

simulationは`SimulationSpec`、`PlayerController`、`SimulationSession`、
`SimulationRunner`、`SimulationStep`、`SimulationLimits`、`SimulationResult`を公開する。
一局の作成または復元、Agent呼出し、action適用、phase進行、終了判定だけを所有する。

リポジトリ、HTTP、provider preflight、反復、統計、checkpoint、成果物保存は所有しない。
Notebook、gameplayレビュー、Agent driver、workerを同じstep APIへ移し、固有のゲームループを削除する。

完了条件は、すべてのヘッドレス入口が同じ実行経路を使い、同じSpecとseedから同じstep、
state、event列を得ることである。

実装は完了している。Notebook、gameplayレビュー、Agentレビュー、prepared game driver、workerは
`SimulationSession`を使用する。applicationの手動action、Agentを使わないphase進行、replay検証は
それぞれの所有境界に残し、別の自動ゲームloopとして扱わない。prepared transitionは開始phase/dayと
完了状態を検証し、phaseの二重進行と進行漏れを拒否する。

### 6. Experiment SDKを完成させる

experimentsは`ExperimentSpec`、`RulesCondition`、`AgentCondition`、`TrialPlan`、
`TrialRunner`、`Evaluator`、`TrialResult`、`ExperimentReport`を公開する。
Rules実験とAgent実験は別の条件型にし、paired seed、席順・役職・personaのローテーション、
checkpoint、resume、provenanceを共通化する。

標準Evaluatorは合法行動率、fallback率、陣営別勝率、生存率、投票先、能力対象、
任意のbelief校正、latency、token、費用を計算する。LLM judgeは標準判定へ使用しない。
説得と欺瞞は観測指標として扱い、因果効果として断定しない。

成果物は`.werewolf-agent/experiments/<experiment-id>/`へ保存する。Trial IDは条件、seed、
割当、実装fingerprintから決定的に生成し、trialごとのimmutable JSONをatomicに保存する。
Reportは保存済みTrialから再生成する。

完了条件は、外部Rule Packと外部Agentをそれぞれ比較でき、中断再開してもTrialが重複せず、
同じ成果物から同じReportを再生成できることである。

### 7. applicationの組み込み境界を完成させる

現在の`GameApplication`をstateless facadeとして維持する。
in-memory gameリポジトリ、in-memory setupリポジトリ、inlineコマンドexecutor、
single-tenant access policy、application factoryを追加する。

完了条件は、HTTP、database、workerを起動せずPythonプロセスへapplicationを組み込め、
in-memoryとSupabaseが同じリポジトリcontractテストを通ることである。

### 8. APIとworkerを新しいSDKへ接続する

composition rootはRule Pack ProviderとAgent Factoryを明示登録する。
APIはpublic state、プレイヤーobservation、public timeline、available action descriptor、
game versionまたはETag、timeline cursor、安定したerror codeを公開する。

設定からパッケージをインストールしたり、任意モジュールをimportしたりしない。
workerはapplicationからprepared gameを受け取り、Simulation実行後にapplicationの
コミット境界で永続化する。

完了条件は、API routeがapplication公開contractだけを呼び、OpenAPIから独立した
Webまたはmobile clientを構築できることである。

### 9. Streamlitと開発者体験を完成させる

Streamlitは設定、プレイ、観戦、物語、記録、再戦に集中する。
大量試行、統計、モデル比較の画面は追加しない。

Domain、Setup、Rule Pack、Agent、Simulation、Experiment、Applicationの最小例を用意する。
外部実装向けcontractテストkitと診断手順を公開する。

完了条件は、自動E2E、desktop、mobile、keyboard、loading、競合、再接続、終了、エラーの
画面確認が完了し、公開例が内部モジュールをimportしないことである。

### 10. 1.0.0をリリースする

全機能を含む`1.0.0rc1`を先に公開する。RC以降は公開契約の修正と不具合修正だけを行い、
新機能を追加しない。

PyPI、GHCR、GitHubリリースは同じコミットから生成し、version、revision、digestを一致させる。
正式版はRCで確認した機能を変更せず、versionとリリース文書だけを更新する。

## 品質ゲート

各変更はformatter、Ruff、mypy、対象テスト、Focusを通す。develop向けPRはCheckを必須とする。
1.0.0rc1はリリース品質、Deep、対応Python版、Supabase、API、worker、ブラウザー、パッケージ、
containerの検査を通す。

品質判定はFake、fixture、localhost、Compose内serviceだけで完結させる。
有料providerと任意の外部APIを必須検査へ使用しない。

実験結果の`complete`、`partial`、`invalid`、`insufficient`と、品質判定の`passed`、
`failed`、`blocked`、`error`を分離する。性能が悪化した実験でも、実行と記録が契約を
満たす場合は品質上の失敗にしない。

## 開発運用

段階1から6までは直列で進める。各段階は最新`develop`から短期branchを作り、
旧path、重複、fallbackを同じ段階で削除する。

develop向けPRは最新headの必須checkと未解決指摘を確認し、merge commitで取り込む。
main向けPRのheadは`develop`に限定し、正式な承認とmergeは人間が行う。
リリース後にmainをdevelopへ逆mergeしない。

## 1.0.0の対象外

- 0.x setup、replay、保存データの互換移行
- 任意phaseと任意action type
- 任意コードを記述できるRule DSL
- 外部実装の自動探索
- 信頼できないpluginのsandbox実行
- 分散実験
- 自動prompt探索
- fine-tuningとreinforcement learning
- 標準LLM judge
- 実験管理Web dashboard
- 外部frontendとmobile clientの実装
- 世界線とwhat-if UI
