# Werewolf Agent

LLM agent を人狼ゲームのプレイヤーとして動かす Python backend です。
deterministic domain core がゲームの真実を管理し、外側には public state と public timeline だけを返します。

## 現在地

- CLI / Streamlit は `GameApi` port 経由で Supabase Data API または local demo API に接続する
- Supabase ログイン時は game、履歴、個人観測、LLM trace を Supabase に保存する
- Supabase 未ログイン時は local demo API が usecase を直接実行し、既定の FakeListLLM で 1 game を完走できる
- Supabase queue worker は operation request を処理し、LLM 呼び出しを CLI / Streamlit process から分離する
- role、rule、scenario、LLM player、prompt、fake response、Streamlit i18n / CSS / screen は runtime definition として読み込む
- manual player token、API key、Supabase secret、private state は public response、public timeline、運用ログへ出さない

## 起動

local demo:

```bash
uv sync --group dev --extra llm --extra streamlit --extra worker
uv run werewolf-agent doctor
uv run werewolf-agent play --role-count werewolf=1 --role-count seer=1 --role-count knight=1 --role-count villager=3 --seed 1
```

Streamlit:

```bash
uv run --extra streamlit streamlit run backend/src/werewolf_agent/entrypoint/streamlit/app.py
```

Supabase queue worker を使う場合:

```bash
supabase migration up
uv run --extra worker werewolf-agent-worker run
```

`WEREWOLF_SUPABASE_URL` と `WEREWOLF_SUPABASE_PUBLISHABLE_KEY` が未設定、または login session がない場合、CLI / Streamlit は local demo API を使います。demo mode では Supabase queue worker は不要です。

公開履歴を確認する場合:

```bash
uv run werewolf-agent setup-options
uv run werewolf-agent games
uv run werewolf-agent timeline <game_id> --follow
uv run werewolf-agent replay --timeline .werewolf-agent/logs/game-001.jsonl
```

VS Code では `UI: Streamlit`、CLI 系 config、`Worker: run` を個別に起動します。OneDrive / sandbox の権限差分を避けるため、検証用 cache と screenshot は `%TEMP%\werewolf-agent` 配下、運用ログは `.werewolf-agent/logs` 配下へ置きます。

## LLM Provider

既定は外部ネットワークを使わない LangChain `fake` provider です。

```text
WEREWOLF_LLM_PROVIDER=fake
WEREWOLF_MODEL=fake-list-llm
WEREWOLF_LLM_BASE_URL=
```

LM Studio:

```text
WEREWOLF_LLM_PROVIDER=lmstudio
WEREWOLF_MODEL=auto
WEREWOLF_LLM_BASE_URL=http://127.0.0.1:1234/v1
WEREWOLF_LLM_TIMEOUT_SECONDS=12
WEREWOLF_LLM_MAX_RETRIES=0
WEREWOLF_LLM_MAX_TOKENS=96
```

OpenAI:

```text
WEREWOLF_LLM_PROVIDER=openai
WEREWOLF_MODEL=gpt-4.1-mini
WEREWOLF_LLM_BASE_URL=
OPENAI_API_KEY=<secret>
```

LLM には `AgentObservation` だけを渡します。観測には `available_actions`、action ごとの `legal_targets`、公開 speech / vote history を含めます。admin-only LLM trace には prompt messages、prompt hash、request payload、raw response、parsed decision、error payload、latency を保存しますが、public response、public timeline、operational log には raw prompt、raw response、API key、provider secret を出しません。

## API / Data Source

この repository は backend game HTTP API を提供しません。CLI / Streamlit は `GameApi` port だけを使い、実行時に次のいずれかへ接続します。

| 実装 | 用途 |
| --- | --- |
| `api.supabase` | Supabase Auth / Data API に直接接続し、operation request を enqueue する |
| `api.local_demo` | Supabase 未ログイン時に process-local repository と usecase で game を進める |

管理者向けの reveal、LLM trace、audit は Supabase RLS と `app_metadata.role = admin` で公開範囲を分けます。詳細は [docs/design/api.md](docs/design/api.md) を参照してください。

## 構成

| Path | 責務 |
| --- | --- |
| `backend/src/werewolf_agent/domain/game/` | ルール、状態、観測、勝敗、game event |
| `backend/src/werewolf_agent/domain/llm/` | provider 非依存 observation / decision、LangChain provider |
| `backend/src/werewolf_agent/resources/` | packaged settings、game / LLM definition、prompt、FakeListLLM response |
| `backend/src/werewolf_agent/usecase/jobs/` | `GameService` facade、command / query、repository / telemetry port |
| `backend/src/werewolf_agent/usecase/internal/` | workflow、projection、agent adapter、唯一の domain 接点 |
| `backend/src/werewolf_agent/api/` | `GameApi` port、factory、usecase bridge、setup options |
| `backend/src/werewolf_agent/api/local_demo/` | 未ログイン用 process-local game API |
| `backend/src/werewolf_agent/api/supabase/` | Supabase Auth / Data API client と session store |
| `backend/src/werewolf_agent/api/supabase/worker/` | Supabase queue worker、Postgres repository、LLM trace sink |
| `backend/src/werewolf_agent/entrypoint/cui/` | Typer CLI、Supabase login、`GameApi` port 経由の操作 |
| `backend/src/werewolf_agent/entrypoint/streamlit/` | Streamlit 画面、状態、表示 model |
| `backend/src/werewolf_agent/entrypoint/requests.py` | CLI / Streamlit 共通の request builder |
| `backend/src/werewolf_agent/contracts/` | Pydantic 外部契約、error code、Problem Details |
| `backend/src/werewolf_agent/commons/` | configuration、resources、logging、message catalog、redaction、shared helper |

## 設定とログ

設定 default は `backend/src/werewolf_agent/resources/settings/defaults.toml` が正です。`.env.example` は override 例だけを置きます。

`commons.configuration` が設定と logging bootstrap を解決し、`commons.resources` が packaged default と外部 TOML を検証します。`api.usecase_bridge` は読み込まれた値だけを usecase へ注入します。domain と usecase は source path、packaged fallback、`.env`、Supabase、logging 設定を知りません。

Supabase client は `WEREWOLF_SUPABASE_URL` / `WEREWOLF_SUPABASE_PUBLISHABLE_KEY`、worker は `WEREWOLF_SUPABASE_DB_DSN` を使います。API page size は `WEREWOLF_API_GAME_LIST_DEFAULT_LIMIT` / `WEREWOLF_API_GAME_LIST_MAX_LIMIT`、timeline は `WEREWOLF_API_TIMELINE_DEFAULT_LIMIT` / `WEREWOLF_API_TIMELINE_MAX_LIMIT`、既定 narration は `WEREWOLF_GAME_DEFAULT_NARRATION_MODE` で変更できます。

Streamlit の文言、CSS、画面配置は `resources/streamlit/` の packaged default を使います。`WEREWOLF_STREAMLIT_I18N_FILE`、`WEREWOLF_STREAMLIT_CSS_FILE`、`WEREWOLF_STREAMLIT_SCREENS_FILE` を指定すると外部ファイルで丸ごと差し替えます。

運用ログは JSON Lines です。既定出力先は `.werewolf-agent/logs/werewolf-agent.jsonl` です。script、VS Code、Docker Compose は `.werewolf-agent/logs` を使い、worker は `worker.jsonl`、Streamlit は `streamlit.jsonl`、CLI は `cli.jsonl`、migration は `migrate.jsonl` に出します。

## 検証

```bat
scripts\check-all.cmd --keep-going
```

個別に確認する場合:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy backend/src
uv run --no-sync ruff check --no-cache --select D --ignore D100,D104 backend/src/werewolf_agent
supabase migration up
uv run --extra worker werewolf-agent-worker run
docker compose build
docker compose --profile worker up worker
docker compose run --rm test
uv run --group docs --extra streamlit sphinx-build -b html -c docs/sphinx docs docs/sphinx/_build/html
```

## 未実装

- 実 provider の長時間 QA と evaluation workflow
- 複数 manual player
- React UI

## License

MIT License
