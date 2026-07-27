(application-api)=
# アプリケーションと API

applicationは利用者の要求をdomain操作へ変換し、保存と公開DTOの生成を調整する。
HTTP API は認証、wire schema、エラー応答を受け持つ。ユースケースごとの認可はapplicationが
`AccessPolicy`を通じて完結させる。

## アプリケーション境界

Python 利用者向けの公開面は stateless な `GameApplication`、`Actor`、application固有の
command、result、portと、作成commandに必要な`LocalRulesDefinition`である。
HTTP request schemaは公開面に含めない。
handler は repository port から集約を読み、domain の操作を呼び、結果を保存して
公開DTOへ射影する。application自身はログやtelemetryを出力しない。
seed未指定の作成要求はapplicationが具体的なseedへ確定し、その値を結果、状態、command記録へ
一貫して保存する。以後の処理は暗黙の乱数源を使用しない。

repository port は保存先の技術を規定しない。in-memory 実装と Supabase 実装は同じ
契約に従い、applicationからdatabase SDKやSQLを隠す。
game一覧はfacadeが受け取った`Actor.user_id`をqueryへ固定し、repository portが参加関係を
検索条件として適用する。request-scoped adapterの暗黙状態だけに認可主体を依存させない。

## HTTP API

FastAPI は application composition root として、設定、repository、認証 adapter、
`GameApplication` を組み立てる。API は次を保証する。

- bearer token を検証し、操作主体を `Actor` へ変換する。
- 認証済みprincipalを`Actor`へ変換する。
- Pydantic 契約で入力と出力を検証する。
- 安全な例外だけを Problem Details へ変換する。
- stack trace と token を応答へ含めず、private state を通常応答へ含めない。

CORSはAPIの一般的な外部境界として扱う。既定では無効とし、
`WEREWOLF_API_CORS_ORIGINS`へ許可originを明示した場合だけmiddlewareを有効にする。

完全状態を返す reveal は通常の game route と `GameClient` port から分離する。管理者
認可と `reveal_api_enabled` の両方を満たす専用 route だけが reveal DTO を返す。
整合性、operation、LLM 利用量の診断 API は private payload を返さない。

## 操作の流れ

1. クライアントが generated contract に従って HTTP 要求を送る。
2. API が認証と入力検証を行う。
3. `GameApplication` が認可し、集約を取得して domain 操作を呼ぶ。
4. repository が更新後の完全状態を保存する。
5. projection が閲覧者向けの公開 DTO を作る。
6. API が公開応答を返し、外部境界で観測情報を記録する。

同一操作の再送、競合、存在しない game、許可されない操作は、domain エラーと
infrastructure エラーを混同せず、安定した error code で表す。

## Worker

worker は queue 取得、operation dispatch、transaction lifecycle、完了時の観測だけを
調整する。PGMQ操作、参加者確認、完了・失敗記録、private view materialize のSQLは
`SupabaseWorkerStore`が所有する。自動進行は準備、DB外計算、version付きcommitへ分け、
古い計算結果を保存しない。commitもapplication facadeがactorを認可してから保存する。
APIとworkerはprocess所有poolからconnectionを借用し、
repositoryとstoreはtransactionを開始しない。

## 契約の管理

外部契約は`werewolf_agent.contracts`に置き、`contracts/openapi.json`を正本とする。
公開HTTP schemaはOpenAPIから生成し、
手書きの HTTP 型を並行して管理しない。CLI と Streamlit は `GameClient` port と
public wire schema を使い、domain や repository を直接 import しない。
winnerと公開factionは`village`、`werewolf`のenumを使い、clientだけの別名を持たない。
