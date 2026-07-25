# Runtime設定とDocker

## 設定の分類

| 種類 | 例 | 公開 |
| --- | --- | --- |
| Secret | DB DSN、service key、provider API key | 不可 |
| Public runtime | preset、game上限、feature flag、契約version | `/api/v1/config` |
| UI | theme、spacing、breakpoint、motion | `/api/v1/config` |

frontendのbuild-time設定はAPI URL、Supabase Auth URL、publishable keyだけです。秘密値はimage、JavaScript、DOMへ渡しません。

APIのbody size、timeout、rate limit、同時実行数はそれぞれ
`WEREWOLF_API_MAX_BODY_BYTES`、`WEREWOLF_API_MESSAGE_MAX_CHARS`、
`WEREWOLF_API_TIMEOUT_SECONDS`、
`WEREWOLF_API_RATE_LIMIT_*`、`WEREWOLF_API_MAX_CONCURRENT_REQUESTS`で変更できます。
Swagger UIとHTTP OpenAPI endpointは`WEREWOLF_API_DOCS_ENABLED`で明示的に有効化した
開発環境だけへ公開し、既定値とComposeのproduction相当設定では無効にします。
UIのtheme、spacing、responsive境界、motion、operation pollingは`WEREWOLF_UI_*`で
変更し、検証後の値だけを`/api/v1/config`へ公開します。
React、Streamlit、CLIは公開設定をHTTP APIから取得します。入力上限などのサーバー制約を
UI serviceへ重複注入せず、必須fieldを持つ型付き契約として検証します。

## Service

`compose.yaml`は`migrate`、`api`、`worker`、`frontend`、`streamlit`、`test`、`e2e`を分離します。migration完了後にAPIとworkerを起動し、healthcheck成功後にUIをreadyにします。有料provider keyはworkerだけへ注入します。

```bash
supabase start
docker compose --profile dev up --build
docker compose --profile test run --rm test
powershell -ExecutionPolicy Bypass -File scripts/run-e2e.ps1
```

Supabase local stackはSupabase CLIがDocker上へ構築します。host実行には
`WEREWOLF_SUPABASE_DB_DSN`、Composeにはcontainerから到達できる
`WEREWOLF_COMPOSE_SUPABASE_DB_DSN`を設定します。local stackの既定例はそれぞれ
`127.0.0.1:54322`と`host.docker.internal:54322`です。同じ名前を使い回して
container内のloopbackへ誤接続しないよう分離します。
`migrate` serviceも`supabase_migrations.schema_migrations`を正として使うため、Supabase CLIと
Composeのどちらから実行しても適用済みmigrationを再実行しません。
E2E scriptはone-shotの`migrate`を先に完了させてから常駐serviceを起動します。
`--abort-on-container-exit`で正常終了したmigrationが全serviceを停止する構成にはしません。
Playwrightは専用image内で`npm ci`し、hostの`node_modules`やread-only workspaceへ依存しません。
テスト本体とvisual baselineはPlaywright設定に隣接する`frontend/e2e`へ配置します。
Docker build contextから全階層の`node_modules`を除外します。

local Supabaseへcontainerから接続するURLとJWTの`iss`は異なるため、E2E scriptは
`WEREWOLF_SUPABASE_JWT_ISSUER`と`WEREWOLF_SUPABASE_JWKS_URL`を別々に設定します。
workerは一時的にDBへ接続できない場合、接続情報をログへ出さず、設定済みpoll間隔で
再試行します。

backendとfrontendはmulti-stage build、runtimeは非root userです。production相当ではStreamlitとtest serviceを起動しません。

CIはfrontendのlockfile install、依存監査、生成client差分、unit test、lint、buildを
個別に検証します。backendの`dev` imageだけに`tests`と構造テストが読むrepository設定・
文書・frontendを含めます。DBを必要としないunit test serviceにはruntime設定を注入せず、
migrationや常駐serviceへの依存も持たせません。runtime imageへtest codeやrepository文書は
含めません。
