(system-architecture)=
# システムアーキテクチャ

Werewolf Agentは、決定的なゲーム実行、LLMによる意思決定、HTTPサービス、利用者クライアントを
分離したPythonバックエンドである。完全なゲーム状態はバックエンドだけが保持し、利用者には公開状態、
public timeline、認証したプレイヤー本人のobservationだけを返す。

## システム境界

```{image} ../_generated/architecture/system-context.svg
:alt: 利用者、Werewolf Agent、Supabase、LLM provider、ローカル成果物の接続関係
:width: 100%
```

プレイヤーと観戦者はStreamlitまたはCLIを使用し、管理者は専用の認可を通過した操作だけを使用する。
Python利用者は公開SDKからdomain、setup、Agent、Simulation、Experimentを直接組み立てられる。

SupabaseはAuth、永続化、非同期operation queueを担当する。LLM providerはAgentの構造化判断だけを返し、
ゲーム状態を参照または変更しない。Experimentと品質実行の成果物はリポジトリ外の管理領域へ保存する。

## 実行プロセス

```{image} ../_generated/architecture/runtime-processes.svg
:alt: Streamlit、CLI、API、worker、application、Simulation、domain、Agentの実行関係
:width: 100%
```

APIプロセスはHTTP入力、認証、wire schema変換、application呼び出し、operation受付を担当する。
workerプロセスはqueueから取得した操作をapplication、Simulation、Agent、外部アダプターへ接続する。
長時間のAgent判断中はdatabase transactionを保持せず、計算後にleaseとgame versionを再確認して保存する。

CLIとStreamlitはHTTP APIだけを使用する。API routeはapplicationの公開contractだけを呼び、
workerだけがapplication、Agent、Simulation、Supabase、LLMアダプターを一つの実行経路へ組み立てる。

## Pythonパッケージ

| パッケージ | 所有する責務 |
| --- | --- |
| `domain` | `Game`、immutable state、event、Rule Policy、状態遷移 |
| `setup` | setup定義、意味検証、seed、checksum、roster生成 |
| `agents` | provider非依存のobservation、decision、Agent session契約 |
| `simulation` | 一局のAgent呼び出し、action適用、phase進行、停止と再開 |
| `experiments` | paired seed、割当rotation、複数Trial、評価、report |
| `application` | use case、認可、transaction、コマンド、result、port、projection |
| `adapters` | Supabase、HTTP client、LangChain、外部I/O |
| `contracts` | HTTP wire schema、error、Problem Details |
| `settings` | runtime設定、環境変数、構成間検証 |
| `security` | principal、credential境界、redaction |
| `observability` | 構造化ログ、context、event sink |
| `api` | FastAPI route、middleware、API composition root |
| `worker` | queue consumer、lease、worker composition root |
| `clients` | CLI、Streamlit、表示model |

```{image} ../_generated/architecture/layer-dependencies.svg
:alt: 実ソースコードのimportから生成したPython layer間の依存
:width: 100%
```

矢印はimportする側からimportされる側へ向く。構造規則は`scripts/architecture/rules.toml`に置き、
実ソースコードのASTから許可依存、循環、公開面、例外を検査する。

## 公開Python SDK

```{image} ../_generated/architecture/public-sdk.svg
:alt: domain、setup、agents、simulation、experiments、applicationの公開依存関係
:width: 100%
```

公開モジュールは`werewolf_agent`、`werewolf_agent.domain`、`werewolf_agent.setup`、
`werewolf_agent.agents`、`werewolf_agent.simulation`、`werewolf_agent.experiments`、
`werewolf_agent.application`に限定する。package直下は`__version__`だけを公開し、利用者は型と操作を
所有するモジュールから直接importする。

公開Python API、内部モジュール、HTTP wire schemaは別の互換性境界である。HTTP契約は
`contracts/openapi.json`、公開Python objectは責務別モジュールのdocstringから生成する。

## 依存境界

- `Game`だけがゲーム状態を変更する。
- `domain`は標準libraryと`domain`内部だけに依存する。
- `setup`は標準library、`domain`、`setup`内部だけに依存する。
- `agents`は`domain`と`application`へ依存しない。
- `simulation`は`agents`、`domain`、`setup`だけに依存する。
- `experiments`は`agents`、`domain`、`setup`、`simulation`だけに依存する。
- `application`は`domain`、`setup`、`application`内部だけに依存する。
- 外部I/Oとframeworkは`adapters`、`api`、`worker`、`clients`の所有境界から内側へ持ち込まない。
- package resourceと外部fileのI/O、provider探索、database接続はcomposition rootまたはアダプターに置く。
- `api/bootstrap.py`から`adapters`への依存だけをHTTP composition rootの明示例外とする。

ゲーム状態とルールは{doc}`domain`、設定解決は{doc}`game-setup`、HTTPとworkerの処理は
{doc}`application-and-api`、Agent判断は{doc}`agents`、一局実行は{doc}`simulation`、反復比較は
{doc}`experiments`、情報公開範囲は{doc}`data-and-security`で定義する。

## 構造証拠

構造分析は{download}`architecture.json <../_generated/architecture/architecture.json>`、JSON Schemaは
{download}`architecture.schema.json <../_generated/architecture/architecture.schema.json>`、判定は
{download}`assessment.md <../_generated/architecture/assessment.md>`へ出力する。図、分析JSON、判定は
同じ実ソースコードと構造規則から一回の処理で生成する。
