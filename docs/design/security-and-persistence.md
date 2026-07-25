# セキュリティと永続化

## 目的

認証情報、ゲームの秘匿状態、LLM traceを公開契約から分離し、同じ入力から保存結果とリプレイ検証を再現できるようにします。

## 認証とLLM

APIはSupabase JWTの署名、issuer、audience、有効期限をJWKSで検証します。クライアントが指定したprovider、model、利用者区分は採用しません。

- anonymous user: game作成時に`fake`へ固定
- non-anonymous user: game作成時に`paid`へ固定
- admin: JWTの`app_metadata.role`が`admin`

有料providerの設定とAPI keyはworkerだけが読みます。provider障害時は、domainが返した合法候補から決定的に選ぶfallbackへ移ります。既存gameのLLM modeは認証状態が変わっても変更しません。
API受理時のLLM modeをoperationへ固定し、queue待機中にログインしてもfakeからpaidへ
変更しません。workerはpaid operationの利用者が実行時にも非anonymousであることを
再検証します。
既存gameへのcommandをqueueへ保存するときも、現在のJWT区分ではなく保存済みgameの
LLM modeを解決し、監査値と冪等性hashを固定します。

rate limitは、認証前のIP・IPとgameの組み合わせと、JWT検証後の利用者・利用者とgameの
組み合わせを独立したbucketで評価します。未検証JWTのclaimやclient指定の識別子は
利用しません。token refreshやgame IDの変更では、IP単位または利用者単位の上限を
回避できません。期限切れbucketだけを回収し、上限到達後の新規bucketは拒否します。
active bucketを追い出さず、任意キーによるメモリ増加と既存制限の解除を防ぎます。

## 情報境界

| 区分 | 保存先・公開先 |
| --- | --- |
| Public | public projectionと通常API |
| Player private | 認可済みobservation API |
| Administrator | `/api/v1/admin` |
| Secret | worker環境変数とprivate schema |

public responseは専用Pydantic modelから構築します。private modelの継承やfield除外は使いません。Problem Details、ログ、OpenAPIへstack trace、token、role、未解決行動を含めません。
API応答は成功・失敗のどちらにも`Cache-Control: no-store`、`nosniff`、frame拒否、
referrer抑止を共通適用し、private observationやoperation結果をブラウザcacheへ残しません。

React、Streamlit、CLIが共有する`GameClient`は一般利用者向けAPIだけを公開します。
観戦表示はpublic stateとpublic timelineから構築し、通常UIから`/api/v1/admin`へは
到達できません。完全状態とreplay診断は管理APIを明示的に利用する運用ツールだけの
責務です。player private observationはプレイ画面だけで取得し、観戦、履歴、設定画面へ
切り替えたブラウザには取得しません。
`WEREWOLF_REVEAL_API_ENABLED`はprivate reveal projectionの保存と管理APIの完全状態取得へ
同時に適用し、`/api/v1/config`の`features.admin_reveal`から有効状態を確認できます。

非同期commandはAPI受付時だけでなく、worker実行時にも現在の参加者・player seat関係を
再検証します。queue待機中に参加権限が失効したcommandは実行せず、安全な失敗として
記録します。

CLIのSupabase sessionはrepository外のOSユーザープロファイルへ一時fileから原子的に
保存します。POSIXでは保存directoryを0700、access tokenとrefresh tokenを含むfileを
0600へ固定し、WindowsではユーザープロファイルのACLを利用します。

## 永続化

Supabase PostgreSQLをproductionの唯一の永続化先とします。状態変更では次を1 transactionで確定します。

- accepted command
- domain event
- private snapshot
- public projection
- player observation
- asynchronous operation result

`private.llm_traces`、`private.agent_decisions`、`private.audit_events`、
`private.game_player_observations`、`private.game_reveals`、`private.llm_usage`は
Data APIから到達できません。`private` schemaの全tableに加え、FastAPIだけが扱う
publicのゲーム、参加者、projection、operationも`anon`と`authenticated`の
権限を明示的に剥奪します。第一段階の`profiles`、`user_preferences`、
`definition_items`、`retention_runs`を含む未使用tableは削除し、互換用の保存面を
残しません。旧RLS専用の`public.is_admin()`も依存policyごと削除し、Data APIのRPC面へ
互換functionを残しません。新しい構造は
`supabase/migrations/20260724000000_second_stage_baseline.sql`で定義し、適用済みbaselineを
書き換えず`20260725000000_remove_legacy_public_tables.sql`で旧tableを削除します。
適用済みcleanupも変更せず、`20260725010000_remove_legacy_public_rpc.sql`で旧RPCを
削除します。
旧データの互換変換は行いません。

## リプレイ

definition snapshot、seed、engine version、LLM mode、検証済みAgentDecisionを保存します。
各状態変更は一意なversionを持ち、完全状態をprivateな`state_committed` eventとして保存します。
外部LLMは再実行せず、このeventからprivate stateとpublic projectionを再構築して、
保存snapshotとの一致、versionとevent sequenceの連続性、commandとの一対一対応を検証します。
command、event、stateにはcanonical JSONのSHA-256 checksumを付け、最初の不一致versionだけを
管理APIへ返します。private payloadは検証応答へ含めません。
