# 第二段階アーキテクチャ

## 目的

ゲームルールを保持するdomainを変更せず、利用者向け画面、HTTP、非同期処理、
永続化、LLMを交換可能な境界で接続します。すべての画面は同じHTTP契約を利用し、
Python利用者だけが`GameApplication`を直接利用できます。

```text
React / Streamlit / CLI
          |
       HTTP API
          |
   GameApplication
          |
Domain / Supabase / Agents
```

## 配置

| Path | 責務 |
| --- | --- |
| `domain` | ゲーム状態、ルール、イベント、可視性 |
| `usecase` | domain操作、transaction境界、projection、replay |
| `agents` | provider非依存の観測・判断契約とLangChain実装 |
| `adapters` | Supabase、HTTP client、自動プレイヤー接続 |
| `api` | FastAPIのHTTPサーバー |
| `interfaces/worker` | operation取得、自動進行、LLM実行 |
| `interfaces` | CLI、Streamlit、worker |
| `contracts` | 外部request、response、Problem Details |
| `security` | JWT検証、認証・認可、redaction |
| `observability` | 外部境界のログ、trace、監査イベント |
| `frontend` | Reactの本番画面 |
| `frontend/e2e` | ReactとStreamlitへ適用するPlaywright browser test |
| `scripts` | migration、契約生成、検証、起動の開発・運用script |

`api`はUIから独立したHTTP serverです。workerはqueue consumerという実行interfaceとして
`interfaces/worker`へ置きます。`interfaces/api`は作りません。

## 公開面

Pythonの業務入口は`werewolf_agent.usecase.GameApplication`だけです。
handler、repository DTO、永続化modelは`usecase`パッケージから公開しません。
`GameApplication`は検証済み依存関係だけを保持し、game状態や利用者sessionを保持しません。
Pythonのsource distributionも`src`、`pyproject.toml`、README、LICENSEだけに限定します。
画面、Docker、運用script、内部テスト、環境設定例は、ライブラリ配布物へ混在させません。

HTTPの一般利用者向け入口は`/api/v1`、管理者向け入口は`/api/v1/admin`に分離します。
command endpointは`Idempotency-Key`と期待game versionを検証し、operationを
`queued`、`running`、`succeeded`、`failed`のいずれかで返します。

## 依存方向

| 層 | 参照できる層 |
| --- | --- |
| `domain` | `domain` |
| `usecase` | `domain`、`usecase` |
| `agents` | `agents`、`configuration` |
| `adapters` | `usecase`、`agents`、domain公開面、`configuration` |
| `api` | `usecase`、`contracts`、`security`、`observability` |
| `interfaces/worker` | `usecase`、`agents`、`adapters`、`configuration` |
| `interfaces/cli`、`interfaces/streamlit` | `adapters/http`、`contracts`、`configuration` |
| `contracts` | `contracts` |
| `security` | `contracts`、`configuration` |
| `observability` | `contracts`、`configuration`、`security` |

具体adapterの構築は`api/bootstrap.py`と`interfaces/worker/bootstrap.py`だけで行います。
API routeは注入されたapplication portだけを呼び、domain、repository、agentsを
直接参照しません。

## 認証とLLM

認証区分は検証済みSupabase JWTからserverが決めます。anonymous userで作成したgameは
`fake`、非anonymous userで作成したgameは`paid`へ固定し、clientからprovider名やmodel名を
受け取りません。有料providerの秘密情報はworkerだけへ渡します。

provider障害、出力不正、利用上限超過時は、domainが返した合法候補から決定的fallbackを
選びます。途中で利用者の認証区分が変わっても既存gameのLLM modeは変更しません。

## 情報境界

- Public: フェーズ、日数、生死、公開発言、解決済み投票
- Player private: 本人の役職、能力、結果、合法候補
- Administrator: 完全状態、replay診断、LLM trace、利用量
- Secret: API key、refresh token、service key、DB認証情報

public responseは専用のallowlist型から構築します。private型を継承してfieldを除外する
方式は使用しません。LLM traceはprivate schemaに保存し、通常APIとSupabase Data APIから
到達できない構成にします。

## 永続化とreplay

Supabaseをproductionの唯一の永続化先とします。状態変更ではaccepted command、
domain event、private snapshot、public projection、player observation、operation結果を
同じtransactionへ保存します。

definition snapshot、seed、engine version、LLM mode、検証済みAgentDecisionを保存し、
外部LLMを再実行せずにeventから状態とprojectionを再構築します。command、event、stateの
canonical JSONへSHA-256 checksumを付け、最初の不一致versionをreplay診断として返します。
通常のreplay responseへprivate payloadは含めません。

## 画面

React、Streamlit、CLIのゲーム通信はHTTP APIだけを使います。ReactからSupabaseへ直接
接続できるのはAuthだけです。合法行動、対象候補、勝敗、フェーズ進行を画面で再計算せず、
APIのprojectionをそのまま表示します。

Reactを本番画面、Streamlitを同じ機能と入力制約を持つ検証用画面とします。
Streamlitの利用者向け本文には開発上の位置付けを表示しません。

browser testはfrontendのPlaywright設定と依存を共有するため`frontend/e2e`へ配置します。
migration適用とOpenAPI出力は独立した製品層ではないため、トップ階層を増やさず
`scripts`へ配置します。トップ階層の`e2e`と`tools`は構造テストで禁止します。
