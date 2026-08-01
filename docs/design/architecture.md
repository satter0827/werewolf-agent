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
| `simulation` | 単一ゲームのAgent呼び出し、action適用、phase進行、停止・再開 |
| `experiments` | paired seed、割当rotation、複数試行、評価、checkpoint、report |
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
- simulationはagents、domain、setupだけを参照し、I/O、永続化、provider設定を所有しない。
- experimentsはagents、domain、setup、simulationだけを参照し、外部providerの探索を行わない。
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

`GameSetupDocument` 0.6.0はmechanics、theme、プレイヤー generationを一つの完全な文書として扱う。
同梱templateと保存revisionは同じschemaを使い、コードは既定役職、既定人数、固定プレイヤーを
所有しない。`setup`がimmutableな完全setup、意味検証、プレイヤー generation、用途別seed、checksum、
Domain Rule Definition変換を所有する。役職はidentity faction、victory team、ability IDだけを持つ。
applicationとHTTPは入力境界のshapeをPydanticで検証し、意味検証は`setup`の標準ライブラリ契約へ委譲する。
公開narrationは単純なallowlist field置換だけを許し、format指定とconversionを拒否する。rendererは
保存済み定義を再信頼せず、出力上限まで逐次構築して上限超過を公開eventへ含めない。
domainの`build_game_rules()`は変換済みRule Definitionから決定的な実行規則を構築する。
replay 0.7.0はgenesis setupとRule Pack manifestを再検証し、agent actionを生成順で保持する。復元時は明示登録済みproviderの
contract version、implementation version、fingerprintが保存値と一致する場合だけ実行する。

ゲーム作成routeはtemplate、保存revision、inline documentのいずれかをrequest時点で解決する。
roster seed確定、プレイヤー生成、checksum計算まで完了した正規化コマンドだけをqueueへ保存し、workerは
template resourceや保存revisionを再解決しない。利用者が指定できるroster seedはプレイヤー生成だけに使う。
applicationは独立した非公開runtime seedを生成し、private strategy、role assignment、gameplayの
乱数をそのseed内でSHA-256 namespace分離する。

本人の保存設定は`private.user_setups`と`private.user_setup_revisions`へ保存する。revisionは追記専用で、
親行lockと`expected_revision`により競合を検出する。所有者ごとのsetup総数とsetupごとのrevision総数を
設定で制限し、新規setup作成は所有者単位のtransaction lockで上限判定を直列化する。一覧と履歴は
設定されたpage size以内だけを取得する。リポジトリは全queryへ所有者条件を付け、private
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
applicationは最小の`RulePackRegistry` Protocolだけに依存する。API、組み込みapplication、workerの
composition rootは組み込みproviderまたは利用者が構築したregistryを明示注入する。

`RulePackManifest`はcontract version、implementation version、fingerprintを保持する。
`AbilityPolicy`は検証済みのnight actionから`NightResolution`、新たな死亡から順序付き
`DeathReactionResolution`、完全stateからobserver非依存の`KnowledgeResolution`を返す。
能動能力、immunity、vulnerability、death reaction、knowledgeの解決意味論を所有する。
Domainは死亡適用、発動条件、使用回数、履歴、eventに加え、knowledge能力の所有、開始時期、
detail、visibilityを検証する。本人roleと設定済み死亡公開はPolicyの主張で上書きできない。
`VictoryPolicy`はimmutableな`GameState`から`WinResult`だけを返す。
`VotingPolicy`は検証済みのpending voteから`VoteResult`だけを返し、投票の合法性、死亡、
履歴、eventはDomainが所有する。Gameは各Outcomeを新しい`GameState`へ適用する際に整合性を
検証し、不正Outcomeまたは例外では元のstateと乱数状態を維持する。

`DiscussionPolicy`は議論開始時のroundと、検証済み提出から`DiscussionResolution`を返す。
組み込み規則はsealedな`opening`を全員分まとめて公開し、公開済みopeningのIDを選ぶorderedな
`response`へ進む。この組を`cycles_per_day`回だけ反復し、既定値を1とする。Domainは提出者、
発言長、参照ID、Policyが返す発言とround遷移を検証し、公開前のopeningを観測へ含めない。
議論の正本は`DiscussionMove`であり、`utterance`は表示文、`topic_id`は対象命題、`position`は
`support`、`oppose`、`undecided`、`relation`は他発言との関係を表す。responseは参照openingの
topicを継承し、`support`、`challenge`、`revise`をpositionと発言履歴に対して検証する。未提出者も
stage完了時にpassとして公開履歴へ確定する。投票evidenceは投票対象本人、対象topicの発言、または
対象の当日passに限定する。

## Agent意思決定と単一ゲーム実行

`agents`はprovider非依存の`AgentFactory`、ゲームとプレイヤーに分離した`AgentSession`、
秘匿性検証済み`DecisionRequest`、構造化`DecisionResponse`を所有する。外部LLMアダプターは
schema検証後のresponseだけを返し、simulationは本人用`GameView`からrequestを構築する。
手続き型の意思決定は`AgentProcedure`でprocedure、stage、cycle、submission modeを伝え、
構造化議論では`opening`と`response`を合法参照だけでなく現在の手続き段階としてLLMへ渡す。

`SimulationRunner`は一局の`Game`、プレイヤー別controller、用途別seed、実行上限を固定する。
`SimulationSession.step()`はAgent action、manual action、phase進行のいずれか一つだけを適用し、
手動入力待ち、終局、上限、cancelを明示的な停止理由として返す。リポジトリ、HTTP、provider preflight、
複数試行、統計、artifactは所有しない。状態・event・action/response列は同じ入力とseedで再現できる。
`latency_ms`は運用診断値であり、決定性の比較対象に含めない。
能力残数などの可変metadataは`AgentMetadataProvider`が本人用`GameView`から都度解決する。
workerは`WorkerDependencies.agent_factories`からプレイヤーID別factoryを注入し、未指定seatだけを
既定のLangChainアダプターで構築する。外部factoryの探索や設定値からの動的importは行わない。

modelには利用可能な行動、行動別の合法対象、発言長、応答可能な発言IDと本文、型付き公開evidence、
対象別の最新position、直前の投票をまとめたargument ledgerを渡す。全履歴は再投入しない。
modelが返した行動や対象は書き換えず、不正値は再問い合わせせずfallbackへ送る。`player_id`はmodelに
生成させず、検証後にserverが付与する。行動が一意で対象や発言が不要な場合だけmodel呼び出しを省略する。

ゲーム単位の`deliberation_level`は`quick`、`standard`、`deep`のいずれかとし、参照する公開event数と
最大出力だけを変える。すべてのレベルで意思決定あたりのmodel呼び出しは最大1回とする。

## 公開面

Pythonの公開モジュールは`werewolf_agent`、`werewolf_agent.application`、
`werewolf_agent.agents`、`werewolf_agent.domain`、`werewolf_agent.experiments`、
`werewolf_agent.simulation`、
`werewolf_agent.setup`に限定する。
package直下は`__version__`だけを公開し、型と関数は責務を所有する公開モジュールからimportする。
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
