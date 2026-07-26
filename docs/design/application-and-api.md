(application-api)=
# アプリケーションと API

applicationは利用者の要求をdomain操作へ変換し、保存と公開DTOの生成を調整する。
HTTP API は認証、認可、wire schema、エラー応答を受け持つ。

## アプリケーション境界

Python 利用者向けの公開面は stateless な `GameApplication` と `Actor` である。
handler は repository port から集約を読み、domain の操作を呼び、結果を保存して
公開DTOへ射影する。application自身はログやtelemetryを出力しない。

repository port は保存先の技術を規定しない。in-memory 実装と Supabase 実装は同じ
契約に従い、applicationからdatabase SDKやSQLを隠す。

## HTTP API

FastAPI は application composition root として、設定、repository、認証 adapter、
`GameApplication` を組み立てる。API は次を保証する。

- bearer token を検証し、操作主体を `Actor` へ変換する。
- game ID を含む要求の所有権と参加権限を検証する。
- Pydantic 契約で入力と出力を検証する。
- 安全な例外だけを Problem Details へ変換する。
- stack trace と token を応答へ含めず、private state を通常応答へ含めない。

完全状態を返す reveal は通常の game route と `GameClient` port から分離する。管理者
認可と `reveal_api_enabled` の両方を満たす専用 route だけが reveal DTO を返す。
整合性、operation、LLM 利用量の診断 API は private payload を返さない。

## 操作の流れ

1. クライアントが generated contract に従って HTTP 要求を送る。
2. API が認証と入力検証を行う。
3. `GameApplication` が集約を取得して domain 操作を呼ぶ。
4. repository が更新後の完全状態を保存する。
5. projection が閲覧者向けの公開 DTO を作る。
6. API が公開応答を返し、外部境界で観測情報を記録する。

同一操作の再送、競合、存在しない game、許可されない操作は、domain エラーと
infrastructure エラーを混同せず、安定した error code で表す。

## Worker

worker は queue 取得、operation dispatch、transaction lifecycle、完了時の観測だけを
調整する。PGMQ操作、参加者確認、完了・失敗記録、private view materialize のSQLは
`SupabaseWorkerStore`が所有する。自動進行は準備、DB外計算、version付きcommitへ分け、
古い計算結果を保存しない。APIとworkerはprocess所有poolからconnectionを借用し、
repositoryとstoreはtransactionを開始しない。

## 契約の管理

外部契約は`werewolf_agent.contracts`に置き、`contracts/openapi.json`を正本とする。
React clientはOpenAPIから生成し、
手書きの HTTP 型を並行して管理しない。CLI と Streamlit は `GameClient` port と
public wire schema を使い、domain や repository を直接 import しない。
