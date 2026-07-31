(system-architecture)=
# システムアーキテクチャ

## 目的

ゲームの決定性と秘匿情報をdomainに閉じ、HTTP、worker、画面、database、LLMを
交換可能な境界として接続する。

## 責務

| レイヤー | 責務 |
| --- | --- |
| `domain` | 標準libraryだけで構成するaggregate、immutable state、event、rule policy |
| `setup` | 標準libraryだけで構成するsetup定義、seed、checksum、roster生成 |
| `application` | use case、authorization、transaction、コマンド/result、port、projection |
| `agents` | provider非依存のobservation、decision、プレイヤー port |
| `adapters` | HTTP client、Supabase、LangChain、外部I/O |
| `contracts` | wire schema、error、Problem Details |
| `settings` | runtime設定と環境変数の検証 |
| `security` | principal、redaction |
| `observability` | ログ、context、event sink |
| `api` | HTTPプロセスとcomposition root |
| `worker` | queue consumerとapplication・agentの接続 |
| `clients` | CLIとStreamlit |

```{image} ../_generated/architecture/system-context.svg
:alt: UI、API、worker、domain、Supabase、LLM providerの接続関係
:width: 100%
```

```{image} ../_generated/architecture/layer-dependencies.svg
:alt: Python layer間の実import依存
:width: 100%
```

## 境界

- domainは他layerを参照しない。
- setupはdomainとsetup内部だけを参照する。
- applicationはdomain、setup、application内部だけを参照し、wire schema、外部service、delivery、
  agentsを参照しない。
- agentsはdomainとapplicationを参照しない。
- LangChainはアダプター、workerは独立プロセスとして扱う。
- package resourceと外部定義fileのI/Oおよび相互参照検証はアダプターに置く。
- API routeはapplicationの公開contractだけを呼ぶ。
- CLIとStreamlitはdomain、application、Supabaseを参照しない。
- CLIとStreamlitはHTTP APIを通じてゲームを操作する。
- clientは未認証の`PublicClient`、通常操作の`GameClient`、管理操作の`AdminClient`へ分け、
  admin responseを通常clientへ追加しない。
- `GET /health`はプロセスlivenessだけを示し、`GET /api/v1/status`は依存先の可用性、
  `GET /api/v1/session`は安全な利用者区分を返す。
- database接続失敗はAPIプロセスを停止せず、databaseを必要とするrequestだけを失敗させる。

## ゲーム設定

`GameSetupDocument` 0.2.0はmechanics、theme、プレイヤー generationを一つの完全な文書として扱う。
同梱templateと保存revisionは同じschemaを使い、コードは既定役職、既定人数、固定プレイヤーを
所有しない。`setup`がimmutableな完全setup、意味検証、プレイヤー generation、用途別seed、checksum、
Domain Rule Definition変換を所有する。役職はidentity faction、victory team、ability IDだけを持つ。
applicationとHTTPは入力境界のshapeをPydanticで検証し、意味検証は`setup`の標準ライブラリ契約へ委譲する。
domainの`build_game_rules()`は変換済みRule Definitionから決定的な実行規則を構築する。
replay 0.3.0は同じ標準ライブラリ契約でgenesis setupを再検証する。

ゲーム作成routeはtemplate、保存revision、inline documentのいずれかをrequest時点で解決する。
seed確定、プレイヤー生成、checksum計算まで完了した正規化コマンドだけをqueueへ保存し、workerは
template resourceや保存revisionを再解決しない。roster、role assignment、gameplayの乱数は同じ
game seedからSHA-256 namespaceで分離する。

本人の保存設定は`private.user_setups`と`private.user_setup_revisions`へ保存する。revisionは追記専用で、
親行lockと`expected_revision`により競合を検出する。リポジトリは全queryへ所有者条件を付け、private
schema、権限剥奪、RLSを防御層として重ねる。公開previewはidentityとpublic personaだけを返し、
role assignmentとprivate strategyを返さない。

`api/bootstrap.py`から`adapters`への依存だけをpath単位の例外として登録する。
構造規則の正本は`scripts/architecture/rules.toml`とする。
公開Pythonモジュール、内部実装モジュール、HTTP wire schemaは別の契約として管理する。Sphinxは
公開PythonモジュールのdocstringからAPI HTMLを生成し、モジュールanchorとPython object構造を検査する。
Package rootの`werewolf_agent`は`__version__`だけを公開する。利用者と内部モジュールはroot aliasを
経由せず、値と型を所有する責務別モジュールを直接参照する。

## Rule Pack

`CompiledRuleSet`は`GameConfig`、`RulePackManifest`、副作用を持たないPolicyを一局へ固定する。
外部Rule Packは`RulePackProvider`を実装し、利用者またはcomposition rootが
`RulePolicyRegistry`へ明示登録する。設定値からimport pathを解決せず、自動探索もしない。

`RulePackManifest`はcontract version、implementation version、fingerprintを保持する。
`VictoryPolicy`はimmutableな`GameState`から`WinResult`だけを返す。`VotingPolicy`は検証済みの
pending voteから`VoteResult`だけを返し、投票の合法性、死亡、death reaction、履歴、eventは
Domainが所有する。GameはOutcomeを新しい`GameState`へ適用する際に整合性を検証し、
不正Outcomeまたは例外では元のstateを維持する。能力は挙動を固定した次の縦断sliceで外部化する。

## Agent意思決定

`agents`は`DecisionTask`、`ModelRequest`、`ModelResponse`、`DecisionModel`を所有する。
workerのcomposition rootはゲーム作成時に固定したproviderから`FakeDecisionModel`または
`LangChainChatDecisionModel`を一度だけ選ぶ。以後はproviderに関係なく、観測正規化、context構築、
model呼び出し、JSON正規化、schema検証、合法手検証、決定的fallback、trace記録の順に処理する。

modelには利用可能な行動、行動別の合法対象、発言長、参照可能なプレイヤー IDと公開evidence IDを渡す。
modelが返した行動や対象は書き換えず、不正値は再問い合わせせずfallbackへ送る。`player_id`はmodelに
生成させず、検証後にserverが付与する。行動が一意で対象や発言が不要な場合だけmodel呼び出しを省略する。

ゲーム単位の`deliberation_level`は`quick`、`standard`、`deep`のいずれかとし、参照する公開event数と
最大出力だけを変える。すべてのレベルで意思決定あたりのmodel呼び出しは最大1回とする。

## 公開面

Pythonの公開モジュールは`werewolf_agent`、`werewolf_agent.domain`、
`werewolf_agent.application`に限定する。package直下は`__version__`だけを公開し、
型と関数は責務を所有する公開モジュールからimportする。
applicationは`GameApplication`、`Actor`、外部実装に必要なport、公開methodの型を
公開する。HTTPの正本は`contracts/openapi.json`とする。

`notebooks`はリポジトリ閲覧者向けの実行例を所有する。Notebook固有のFakeゲーム進行と
表示用resultは製品package、wheel、sdistへ含めず、公開APIの互換性対象にしない。

application内部はゲーム参照、進行、プレイヤー action、timelineを独立したhandlerにする。
DTOはruntime context、request、result、persistence recordのlifecycleで分ける。
HTTP routeはwire schemaとapplicationコマンド/resultの変換だけを行い、認可アダプターと
queueアダプターを直接呼ばない。

## 検証

実ソースコードのASTからlayer、モジュール、import元行、cycle、公開面を評価する。結果は
{download}`architecture.json <../_generated/architecture/architecture.json>`、
{download}`architecture.schema.json <../_generated/architecture/architecture.schema.json>`、
{download}`assessment.md <../_generated/architecture/assessment.md>`で確認できる。
