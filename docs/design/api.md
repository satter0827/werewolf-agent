# HTTP API

## 目的

React、Streamlit、CLIが共通利用するHTTP契約を定義します。ゲームルールは
`GameApplication`の内側でのみ実行し、画面はSupabase Data APIへゲームデータを
直接送受信しません。

API versionは`v1`、契約形式はJSONです。失敗はRFC 9457 Problem Detailsで返します。

## 一般利用者向けendpoint

| Method | Path | 用途 |
| --- | --- | --- |
| `GET` | `/api/v1/config` | 公開可能なruntime設定 |
| `POST` | `/api/v1/games` | game作成operation |
| `GET` | `/api/v1/games` | 閲覧可能なgame一覧 |
| `GET` | `/api/v1/games/{game_id}` | public state |
| `GET` | `/api/v1/games/{game_id}/timeline` | public timeline |
| `POST` | `/api/v1/games/{game_id}/actions` | player action operation |
| `POST` | `/api/v1/games/{game_id}/advance` | advance operation |
| `GET` | `/api/v1/operations/{operation_id}` | operation状態 |

管理者向けendpointは`/api/v1/admin`へ隔離します。

command requestは`Idempotency-Key` headerを必須とし、対象gameがある場合は
`expected_version`を必須にします。受理時は`202 Accepted`とoperation IDを返します。
operation statusは`queued`、`running`、`succeeded`、`failed`だけを使用します。
同じkeyと同じrequestの再送は同じoperationを返し、異なるrequestでのkey再利用は
`409 Conflict`として拒否します。
timelineの`limit`はHTTP、`GameApplication`、repositoryまで同じ値を渡し、server側で
上限を検証します。未宣言のqueryを黙って無視しません。

OpenAPIは実際の例外境界と同じ`application/problem+json`の`ProblemDetails`を公開します。
FastAPI既定の`422 HTTPValidationError`は外部契約へ残さず、入力不備は実装と契約の両方で
`400 Bad Request`へ統一します。
Swagger UIとOpenAPI endpointは管理APIの存在を列挙できるため、既定では公開しません。
ローカル開発で必要な場合だけ`WEREWOLF_API_DOCS_ENABLED=true`を指定します。
契約生成はHTTP endpointではなく`create_app().openapi()`を直接使用します。

管理者向けendpoint:

| Method | Path | 用途 |
| --- | --- | --- |
| `GET` | `/api/v1/admin/games/{game_id}/reveal` | 完全状態 |
| `POST` | `/api/v1/admin/games/{game_id}/replay/verify` | replay検証 |
| `GET` | `/api/v1/admin/operations/{operation_id}` | operation診断 |
| `GET` | `/api/v1/admin/games/{game_id}/llm-traces` | prompt本文を除くtrace |
| `GET` | `/api/v1/admin/games/{game_id}/llm-usage` | 利用量集計 |

## 責務

| 層 | 責務 |
| --- | --- |
| `interfaces` | CLI、Streamlit、workerの入力と表示 |
| `adapters` | `GameClient`、Supabase、repository、LLM game driver |
| `usecase` | IDを含む要求、取得、復元、domain呼び出し、DTO変換 |
| `domain` | ゲームルールと状態遷移 |
| `agents` | provider非依存の判断契約とLangChain実装 |
| `configuration` | 環境変数、TOML、packaged defaultの読込と検証 |
| `observability` | 境界ログ、イベント、実行コンテキスト |
| `security` | 秘密情報のマスキング |
| `contracts` | 外部wire schema、error code、Problem Details |

## データフロー

```text
React      -> generated HTTP client --+
Streamlit  -> HttpGameClient ---------+-> FastAPI -> GameApplication -> Game
CLI        -> HttpGameClient ---------+

Python利用者 ----------------------------> GameApplication -> Game

自動プレイヤー:
interfaces/worker -> adapters/agents -> PlayerAgent -> AgentDecision -> Game(Action)
```

自動プレイヤーの接続は`adapters/agents/game_driver.py`に限定します。agentsはdomainが提示した合法対象から候補を返し、domainが提出時に再検証します。LLM失敗時は同じ判断パイプラインのfallbackが合法候補を選びます。

## HTTP client

CLIとStreamlitが参照できるゲームクライアントはHTTP実装だけです。

```python
from werewolf_agent.adapters.http import HttpGameClient
```

ReactはOpenAPIから生成したTypeScript clientを使用します。UIからSupabaseへ直接接続
できるのはAuthだけです。ゲームデータのData API、RPC、Realtime利用は禁止します。

## Usecase

Python利用者向けの公開面は`Actor`と`GameApplication`だけです。

```python
games = GameApplication(context)
games.create(input)
games.get(game_id, actor)
games.submit_action(game_id, actor, action, expected_version)
games.advance(game_id, actor, expected_version)
```

`GameApplication`は検証済み依存関係だけを保持し、game状態やsessionを保持しません。
handler、command/query分類、repository DTOは内部実装です。

1. IDと利用者要求を検証する
2. repositoryから現在状態を取得する
3. `Game.restore()`でdomainを復元する
4. domainの公開操作を呼ぶ
5. revisionを確認して結果を保存する
6. public DTOまたはprivate DTOへ変換する

usecaseには役職、フェーズ、行動対象、勝敗の条件分岐を置きません。
LLMのprovider設定とtrace sinkも`UsecaseContext`へ入れず、`adapters/agents/game_driver.py`の`AgentRuntime`が保持します。

## Agents

公開契約は`PlayerAgent`、`AgentObservation`、`AgentDecision`です。ゲームの内部状態を型として共有しません。

LangChainとLangGraphの具体実装は`agents/langchain`に限定します。fake providerも独自クラスを作らず、LangChain標準の`FakeListLLM`を使用します。fakeと実providerは、prompt構築、構造化出力、検証、再試行、fallbackを共有します。

設定で変更できる項目:

- provider種別
- model名と接続先
- timeout、retry、temperature、max tokens
- decision graph
- prompt
- fake応答列
- validation retryとfallback方針

provider固有の新しい通信方式や新しいgraph nodeはPython実装を必要とします。

## 公開情報と秘密情報

| 出力先 | 許可する情報 |
| --- | --- |
| public state | フェーズ、日数、生死、勝者 |
| public timeline | 公開発言、解決後の投票結果、公開死亡結果 |
| player observation | 本人が観測できる役職、能力、合法候補 |
| admin reveal | 管理者専用の完全状態 |
| LLM trace | private schemaと管理API。管理APIはprompt本文と生応答を返さない |
| operational log | ID、処理結果、所要時間、外部障害の分類 |

public responseとログへ、秘密役職、夜行動対象、占い結果、API key、token、prompt、LLM生出力を出しません。
各プレイヤーの投票提出と投票先は解決前に公開せず、集計済みの結果だけをpublic timelineへ出します。

## ログ

domainとusecaseはログを出しません。interfacesとadaptersが外部境界で一度だけ記録します。

| Level | 用途 |
| --- | --- |
| `DEBUG` | 状態遷移、設定解決、エージェント判断の安全な要約 |
| `INFO` | プロセス開始・終了、ゲーム作成、フェーズ完了、ゲーム終了 |
| `WARNING` | 外部サービスの一時障害、再試行、縮退 |
| `ERROR` | 継続不能な外部障害、不正設定、予期しない例外 |

入力不備、存在しないID、通常のルール違反は結果として返し、エラーログにしません。ログ名は実行機能に合わせて`api.jsonl`、`worker.jsonl`、`streamlit.jsonl`、`cli.jsonl`、`migrate.jsonl`とします。

## 永続化

- Supabaseを永続化の正本とする
- public schemaとprivate schemaの既存分離を維持する
- APIとworkerだけがtransaction内でprivate stateへ接続する
- optimistic revisionを維持し、状態競合を通常の結果として扱う
- public timelineをdomainの型付きイベントから投影する
- baseline migrationでcommand、state event、snapshot、projection、trace、利用量を定義する

## 構造制約

- CLIとStreamlitはdomainとusecaseを直接importしない
- `interfaces/worker`だけが実行interfaceとしてusecaseとagentsを接続する
- adaptersはinterfacesへ依存しない
- usecaseはadapters、interfaces、agentsへ依存しない
- agentsはdomainとusecaseへ依存しない
- domainは他のプロジェクト層へ依存しない
- 外部層は`werewolf_agent.domain`の公開面を使用する
- import許可表と循環参照はASTベースの構造テストで検査する

## エラー契約

domainの`RuleViolation`はusecaseが外部エラー契約へ変換します。外部には安全なerror code、利用者向けメッセージ、必要最小限のcontextだけを返します。内部例外、stack trace、認証情報は返しません。
