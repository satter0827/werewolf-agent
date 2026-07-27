(system-architecture)=
# システムアーキテクチャ

## 目的

ゲームの決定性と秘匿情報をdomainに閉じ、HTTP、worker、画面、database、LLMを
交換可能な境界として接続する。

## 責務

| Layer | 責務 |
| --- | --- |
| `domain` | 標準libraryだけで構成するaggregate、immutable state、event、rule policy |
| `application` | use case、authorization、transaction、command/result、port、projection |
| `agents` | provider非依存のobservation、decision、player port |
| `adapters` | HTTP client、Supabase、LangChain、外部I/O |
| `contracts` | wire schema、error、Problem Details |
| `settings` | runtime設定と環境変数の検証 |
| `security` | principal、redaction |
| `observability` | log、context、event sink |
| `api` | HTTP processとcomposition root |
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
- applicationはdomainとapplication内部だけを参照し、wire schema、外部service、delivery、
  agentsを参照しない。
- agentsはdomainとapplicationを参照しない。
- LangChainはadapter、workerは独立processとして扱う。
- package resourceと外部定義fileのI/Oおよび相互参照検証はadapterに置く。
- API routeはapplicationの公開contractだけを呼ぶ。
- CLIとStreamlitはdomain、application、Supabaseを参照しない。
- CLIとStreamlitはHTTP APIを通じてゲームを操作する。
- clientは未認証の`PublicClient`、通常操作の`GameClient`、管理操作の`AdminClient`へ分け、
  admin responseを通常clientへ追加しない。
- `GET /health`はprocess livenessだけを示し、`GET /api/v1/status`は依存先の可用性、
  `GET /api/v1/session`は安全な利用者区分を返す。
- database接続失敗はAPI processを停止せず、databaseを必要とするrequestだけを失敗させる。

`api/bootstrap.py`から`adapters`への依存だけをpath単位の例外として登録する。
構造規則の正本は`scripts/architecture/rules.toml`とする。

## 公開面

Pythonの公開moduleは`werewolf_agent.domain`と`werewolf_agent.application`に限定する。
applicationは`GameApplication`、`Actor`、外部実装に必要なport、公開methodの型を
公開する。HTTPの正本は`contracts/openapi.json`とする。

application内部はゲーム参照、進行、player action、timelineを独立したhandlerにする。
DTOはruntime context、request、result、persistence recordのlifecycleで分ける。
HTTP routeはwire schemaとapplication command/resultの変換だけを行い、認可adapterと
queue adapterを直接呼ばない。

## 検証

実sourceのASTからlayer、module、import元行、cycle、公開面を評価する。結果は
{download}`architecture.json <../_generated/architecture/architecture.json>`、
{download}`architecture.schema.json <../_generated/architecture/architecture.schema.json>`、
{download}`assessment.md <../_generated/architecture/assessment.md>`で確認できる。
