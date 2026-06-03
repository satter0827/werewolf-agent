# Werewolf Agent

LLM agent を人狼ゲームのプレイヤーとして動かす Python backend です。
deterministic domain core がゲームの真実を管理し、外側には public state と public timeline だけを返します。

## 現在地

- CLI / Streamlit は Supabase に直接接続し、ログインなしでは process-local demo client で game を進められる
- LangChain `fake` provider、LM Studio、OpenAI provider、AI strategy を設定値と UI で切り替えられる
- Supabase queue worker が game 作成、advance、manual action を処理し、LLM 呼び出しを UI / CLI process から分離している
- role、rule、scenario、LLM player、prompt、fake response、Streamlit i18n / CSS / screen は runtime definition として読み込む
- FastAPI の公開面は health check だけに絞り、画面から変更される game / 履歴 / trace は Supabase に保存する
- manual player token、API key、Supabase secret、private state は public response、public timeline、運用ログへ出さない

## 起動

local demo:

```bash
uv sync --group dev --extra api --extra llm --extra streamlit --extra worker
uv run werewolf-agent doctor
uv run --extra api uvicorn werewolf_agent.interface.api.app:create_app --factory
```

別ターミナルで CLI から game を実行します。`WEREWOLF_SUPABASE_URL` と `WEREWOLF_SUPABASE_PUBLISHABLE_KEY` が未設定、または login session がない場合は demo mode で動きます。demo mode では Supabase queue worker は起動しません。

```bash
uv run werewolf-agent play --role-count werewolf=1 --role-count seer=1 --role-count knight=1 --role-count villager=3 --seed 1
uv run werewolf-agent play --role-count werewolf=1 --role-count seer=1 --role-count knight=1 --role-count villager=3 --seed 1 --manual-player player-1
```

公開履歴を確認する場合:

```bash
uv run werewolf-agent setup-options
uv run werewolf-agent games
uv run werewolf-agent timeline <game_id> --follow
uv run werewolf-agent replay --timeline .werewolf-agent/logs/game-001.jsonl
```

Streamlit:

```bash
uv run --extra streamlit streamlit run backend/src/werewolf_agent/interface/entrypoint/streamlit/app.py
```

Supabase queue worker を使う場合:

```bash
supabase migration up
uv run --extra worker werewolf-agent-worker run
```

VS Code では demo 起動用に `App: API + Streamlit` を使います。Supabase queue worker は `WEREWOLF_SUPABASE_DB_DSN` を設定した場合だけ `Worker: run` で別起動します。OneDrive / sandbox の権限差分を避けるため、検証用 cache と screenshot は `%TEMP%\werewolf-agent` 配下、運用ログは `.werewolf-agent/logs` 配下へ置きます。

## LLM Provider

既定は local LM Studio server を使う `lmstudio` provider です。

```text
WEREWOLF_LLM_PROVIDER=lmstudio
WEREWOLF_MODEL=auto
WEREWOLF_LLM_BASE_URL=http://127.0.0.1:1234/v1
WEREWOLF_LLM_TIMEOUT_SECONDS=12
WEREWOLF_LLM_MAX_RETRIES=0
WEREWOLF_LLM_MAX_TOKENS=96
```

LM Studio:

```text
WEREWOLF_LLM_PROVIDER=lmstudio
WEREWOLF_MODEL=auto
WEREWOLF_LLM_BASE_URL=http://127.0.0.1:1234/v1
```

`WEREWOLF_MODEL=auto` は LM Studio の `/v1/models` から最初の loaded model id を取得します。LM Studio server が起動していない場合でも、game 進行中の provider 呼び出し失敗は deterministic fallback で進めます。unsupported provider、依存不足、設定不備は起動または構築時の設定エラーとして扱います。
LM Studio 本体設定は変更せず、timeout、retry、出力 token、job polling、AI strategy はこの repository の設定値で制御します。

OpenAI:

```text
WEREWOLF_LLM_PROVIDER=openai
WEREWOLF_MODEL=gpt-4.1-mini
WEREWOLF_LLM_BASE_URL=
OPENAI_API_KEY=<secret>
```

LLM には `AgentObservation` だけを渡します。観測には `available_actions`、action ごとの `legal_targets`、公開 speech / vote history を含めます。Streamlit では `AI strategy` として `Stable Fast`、`Role Basic`、`Target Ranker` を選べます。選択した `agent_strategy_id` は game config に保存され、demo と worker の advance で同じ strategy を使います。分析・改善のため、admin-only LLM trace には prompt messages、prompt hash、request payload、raw response、parsed decision、error payload、latency を保存しますが、public response、public timeline、operational log には raw prompt、raw response、API key、provider secret を出しません。

## API / Data Source

| Method | Path | 用途 |
| --- | --- | --- |
| `GET` | `/api/v1/health` | health check |

CLI / Streamlit は backend game API を呼ばず、Supabase Data API と Auth を直接使います。未ログイン時は同じ `GameClient` port の demo implementation を使うため、外部 DB なしで試せます。管理者向けの reveal、LLM trace、audit は Supabase RLS と `app_metadata.role = admin` で公開範囲を分けます。

詳細は [docs/design/api.md](docs/design/api.md) を参照してください。

## 構成

| Path | 責務 |
| --- | --- |
| `backend/src/werewolf_agent/domain/game/` | ルール、状態、観測、勝敗、game event |
| `backend/src/werewolf_agent/domain/llm/` | provider 非依存 observation / decision、LangChain provider |
| `backend/src/werewolf_agent/resources/` | packaged settings、game / LLM definition、prompt、FakeListLLM response |
| `backend/src/werewolf_agent/usecase/jobs/` | `GameService` facade、command / query、repository / telemetry port |
| `backend/src/werewolf_agent/usecase/internal/` | workflow、projection、agent adapter、唯一の domain 接点 |
| `backend/src/werewolf_agent/interface/runtime/` | settings、definition loader、logging bootstrap |
| `backend/src/werewolf_agent/interface/application/` | settings から usecase へ渡す依存関係の組み立て |
| `backend/src/werewolf_agent/interface/api/` | health check 用 FastAPI router |
| `backend/src/werewolf_agent/interface/demo/` | 未ログイン用 process-local game client |
| `backend/src/werewolf_agent/interface/supabase/` | Supabase Auth / Data API client と session store |
| `backend/src/werewolf_agent/interface/worker/` | Supabase queue worker、Postgres repository、LLM trace sink |
| `backend/src/werewolf_agent/interface/entrypoint/cui/` | Typer CLI、Supabase login、client port 経由の操作 |
| `backend/src/werewolf_agent/interface/entrypoint/streamlit/` | Streamlit 画面、状態、表示 model |
| `backend/src/werewolf_agent/interface/shared/` | game client port、request builder、diagnostics、共通 adapter |
| `backend/src/werewolf_agent/contracts/` | Pydantic 外部契約、error code、Problem Details |
| `backend/src/werewolf_agent/commons/` | 副作用のない共通値、validation、redaction |

## 設定とログ

設定 default は `backend/src/werewolf_agent/resources/settings/defaults.toml` が正です。`.env.example` は override 例だけを置きます。

`interface/runtime` が設定、definition TOML、logging bootstrap を浅い入口で解決し、adapter から usecase へ値として注入します。domain と usecase は source path、packaged fallback、`.env`、Supabase、logging 設定を知りません。

運用時に変える値は `.env` または環境変数で override します。Supabase client は `WEREWOLF_SUPABASE_URL` / `WEREWOLF_SUPABASE_PUBLISHABLE_KEY`、worker は `WEREWOLF_SUPABASE_DB_DSN` を使います。API page size は `WEREWOLF_API_GAME_LIST_DEFAULT_LIMIT` / `WEREWOLF_API_GAME_LIST_MAX_LIMIT`、timeline は `WEREWOLF_API_TIMELINE_DEFAULT_LIMIT` / `WEREWOLF_API_TIMELINE_MAX_LIMIT`、game 作成時の既定 narration は `WEREWOLF_GAME_DEFAULT_NARRATION_MODE` で変更できます。observer / demo reveal の公開は `WEREWOLF_REVEAL_API_ENABLED`、AI strategy は `WEREWOLF_LLM_DEFAULT_AGENT_STRATEGY_ID`、decision graph 定義は `WEREWOLF_LLM_DECISION_GRAPHS_FILE`、queue polling は `WEREWOLF_ADVANCE_JOB_POLL_INTERVAL_SECONDS` / `WEREWOLF_ADVANCE_JOB_POLL_TIMEOUT_SECONDS`、LLM trace retention は `WEREWOLF_LLM_TRACE_RETENTION_DAYS` で変更できます。

Streamlit の文言、CSS、画面配置は `resources/streamlit/` の packaged default を使います。`WEREWOLF_STREAMLIT_I18N_FILE`、`WEREWOLF_STREAMLIT_CSS_FILE`、`WEREWOLF_STREAMLIT_SCREENS_FILE` を指定すると外部ファイルで丸ごと差し替えます。

運用ログは JSON Lines です。既定出力先は `.werewolf-agent/logs/werewolf-agent.jsonl` です。script、VS Code、Docker Compose は `.werewolf-agent/logs` を使い、API は `api.jsonl`、worker は `worker.jsonl`、Streamlit は `streamlit.jsonl`、CLI は `cli.jsonl`、migration は `migrate.jsonl` に出します。

## 検証

```bat
scripts\check-all.cmd --api --keep-going
```

個別に確認する場合:

```bash
uv run pytest
uv run --extra api pytest tests/integration/api
uv run ruff check .
uv run ruff format --check .
uv run mypy backend/src
uv run --no-sync ruff check --no-cache --select D --ignore D100,D104 backend/src/werewolf_agent
supabase migration up
uv run --extra worker werewolf-agent-worker run
docker compose build
docker compose --profile worker up worker
docker compose run --rm test
uv run --group docs --extra api --extra streamlit sphinx-build -b html -c docs/sphinx docs docs/sphinx/_build/html
```

## 未実装

- 実 provider の長時間 QA と evaluation workflow
- 複数 manual player
- React UI

## License

MIT License
