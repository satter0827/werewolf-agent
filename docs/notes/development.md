# Development

途中参加者が最短で再開するための作業メモです。
完成版の設計は `docs/design/`、Sphinx の入口と設定は `docs/sphinx/` に置きます。

## 現在地

- deterministic domain core 実装済み
- CLI / Streamlit は Supabase に直接接続し、未ログイン時は process-local demo client で game を進められる
- `GameService` facade 経由で create / get / advance / list / timeline / reveal / private observation / manual action を扱う
- FastAPI の公開面は `/health` だけに絞る
- CLI `doctor` / `login` / `logout` / `whoami` / `setup-options` / `new` / `show` / `advance` / `play` / `timeline` / `replay` / `games` は `GameClient` port だけを使う
- Streamlit は Play / Observe / History を提供し、ログイン有無と admin 権限で表示を分ける
- LLM provider の既定は LM Studio。`WEREWOLF_MODEL=auto` で `/v1/models` の先頭 model を使う
- Supabase queue worker が game 作成、advance、manual action を処理し、LLM 呼び出しを UI / CLI process から分離する
- LLM trace は prompt hash、prompt messages、request payload、raw response、parsed decision、error payload、latency を永続化する
- LangChain `fake` と OpenAI provider は設定値で明示的に切り替える
- 複数 manual player、React UI は未実装

## 最初に実行

```bash
uv sync --group dev --extra api --extra llm --extra streamlit --extra worker
uv run werewolf-agent doctor
supabase migration up
```

API:

```bash
uv run --extra api uvicorn werewolf_agent.interface.api.app:create_app --factory
uv run --extra worker werewolf-agent-worker run
```

CLI:

```bash
uv run werewolf-agent setup-options
uv run werewolf-agent play --role-count werewolf=1 --role-count seer=1 --role-count knight=1 --role-count villager=3 --seed 1
uv run werewolf-agent play --role-count werewolf=1 --role-count seer=1 --role-count knight=1 --role-count villager=3 --seed 1 --manual-player player-1
uv run werewolf-agent games
uv run werewolf-agent timeline <game_id> --follow
```

Streamlit:

```bash
uv run --extra streamlit streamlit run backend/src/werewolf_agent/interface/entrypoint/streamlit/app.py
```

## Windows / OneDrive / Codex

この repository は OneDrive の reparse point 配下で作業されることがあります。Codex の sandbox から repository 配下へ新規生成物を書くと、`Access is denied`、Ruff cache warning、SQLite `disk I/O error` が出る場合があります。

検証用 cache と browser QA screenshot は `%TEMP%\werewolf-agent` 配下へ置きます。運用ログだけは `.werewolf-agent/logs` 配下へ統一します。依存関係が同期済みなら `uv run --no-sync ...` を優先し、Ruff は `--no-cache`、mypy は `--no-incremental` または `%TEMP%` の cache を使います。

まとめて検証:

```bat
scripts\check-all.cmd --api --keep-going
```

API と worker を個別に起動:

```bat
scripts\run-api.cmd --reload
scripts\run-worker.cmd --once
```

VS Code の Run and Debug は cache を `%TEMP%\werewolf-agent` 配下へ向けます。運用ログは `.werewolf-agent/logs` 配下へ出し、API は `api.jsonl`、worker は `worker.jsonl`、Streamlit は `streamlit.jsonl`、CLI は `cli.jsonl`、migration は `migrate.jsonl` を使います。

## 配置

| Path | 責務 |
| --- | --- |
| `backend/src/werewolf_agent/domain/game/` | ルール、状態、観測、勝敗、game event |
| `backend/src/werewolf_agent/domain/llm/` | provider 非依存 DTO、LangChain decision provider |
| `backend/src/werewolf_agent/resources/` | packaged defaults、game / LLM definition、prompt、FakeListLLM response |
| `backend/src/werewolf_agent/usecase/jobs/` | `GameService` facade、command / query、repository / telemetry port |
| `backend/src/werewolf_agent/usecase/internal/` | workflow、projection、agent adapter、唯一の domain 接点 |
| `backend/src/werewolf_agent/interface/runtime/` | settings、definition loader、logging bootstrap |
| `backend/src/werewolf_agent/interface/application/` | settings から usecase へ渡す依存関係の組み立て |
| `backend/src/werewolf_agent/interface/api/` | health check 用 FastAPI app、router |
| `backend/src/werewolf_agent/interface/demo/` | 未ログイン用 process-local game client |
| `backend/src/werewolf_agent/interface/supabase/` | Supabase Auth / Data API client と session store |
| `backend/src/werewolf_agent/interface/worker/` | Supabase queue worker、Postgres repository、LLM trace sink |
| `backend/src/werewolf_agent/interface/entrypoint/cui/` | Typer CLI、Supabase login、client port 経由の操作 |
| `backend/src/werewolf_agent/interface/entrypoint/streamlit/` | Streamlit 画面、画面状態、表示 model |
| `backend/src/werewolf_agent/interface/shared/` | game client port、request builder、diagnostics、共通 adapter |
| `backend/src/werewolf_agent/contracts/` | Pydantic 外部契約、error code、Problem Details |
| `backend/src/werewolf_agent/commons/` | constants、messages、validation、definition value、redaction |
| `tests/unit/` | process 内 unit test |
| `tests/integration/api/` | FastAPI health integration test |

## 境界

- CLI / Streamlit は `contracts/schemas.py` と `GameClient` port だけを使う
- `interface/api` と `interface/entrypoint/cui` は domain / usecase を直接 import しない
- interface 層から usecase を呼ぶ場所は `interface/application`、`interface/demo`、`interface/worker`、`interface/shared/setup_options.py` に限定する
- 設定読み込み、definition loading、logging bootstrap は `interface/runtime` に置く
- `interface/application` は `werewolf_agent.usecase.jobs` の top-level 公開面だけを import する
- `usecase/jobs` は domain を import せず、facade、command / query、repository / telemetry port に限定する
- usecase から domain へ入る code は `usecase/internal` 配下に限定する
- `usecase/internal` は interface / wire schema に依存させない
- `domain.game` と `domain.llm` は互いに import しない
- public response / public timeline / operational log に role、night action target、secret、token、API key、raw provider response を混ぜない

## 定義体

| 定義体 | 既定 | override | 渡す先 |
| --- | --- | --- | --- |
| ルール定義体 | `backend/src/werewolf_agent/resources/game/rules.toml` | `WEREWOLF_GAME_RULES_FILE` | `domain.game` |
| ロール定義体 | `backend/src/werewolf_agent/resources/game/roles.toml` | `WEREWOLF_GAME_ROLES_FILE` | `domain.game` |
| Game catalog | `backend/src/werewolf_agent/resources/game/catalog.toml` | `WEREWOLF_GAME_CATALOG_FILE` | `usecase.internal` / `domain.llm` |
| LLM players | `backend/src/werewolf_agent/resources/llm/players.toml` | `WEREWOLF_LLM_PLAYERS_FILE` | `domain.llm` |
| LLM prompt | `backend/src/werewolf_agent/resources/prompts/agent_decision.toml` | `WEREWOLF_LLM_PROMPT_FILE` | `domain.llm` |
| Fake responses | `backend/src/werewolf_agent/resources/llm/fake_responses.toml` | `WEREWOLF_LLM_FAKE_RESPONSES_FILE` | `domain.llm` |
| Streamlit i18n | `backend/src/werewolf_agent/resources/streamlit/i18n.toml` | `WEREWOLF_STREAMLIT_I18N_FILE` | `interface/entrypoint/streamlit` |
| Streamlit CSS | `backend/src/werewolf_agent/resources/streamlit/default.css` | `WEREWOLF_STREAMLIT_CSS_FILE` | `interface/entrypoint/streamlit` |
| Streamlit screen | `backend/src/werewolf_agent/resources/streamlit/screens.toml` | `WEREWOLF_STREAMLIT_SCREENS_FILE` | `interface/entrypoint/streamlit` |

`interface/runtime` が path 解決、packaged default、外部 TOML 読み込み、Pydantic 検証を共通処理で行います。adapter は読み込まれた値だけを usecase へ注入します。game 作成時は `role_counts` から人数を導出し、manual seat は `manual_player_id` で指定します。

Streamlit CSS は追記ではなく置換方式です。画面定義体は表示要素、表示順、配置、列数だけを制御し、public / private 判定、action availability、API payload、game state 計算は `streamlit/app.py` と表示 model 側に残します。

運用値の正本は `backend/src/werewolf_agent/resources/settings/defaults.toml` です。Supabase client は `WEREWOLF_SUPABASE_URL` / `WEREWOLF_SUPABASE_PUBLISHABLE_KEY`、worker は `WEREWOLF_SUPABASE_DB_DSN` を使います。API page size は `WEREWOLF_API_GAME_LIST_DEFAULT_LIMIT` / `WEREWOLF_API_GAME_LIST_MAX_LIMIT`、timeline は `WEREWOLF_API_TIMELINE_DEFAULT_LIMIT` / `WEREWOLF_API_TIMELINE_MAX_LIMIT`、既定 narration は `WEREWOLF_GAME_DEFAULT_NARRATION_MODE` で override します。LLM は `WEREWOLF_LLM_TIMEOUT_SECONDS` / `WEREWOLF_LLM_MAX_RETRIES` / `WEREWOLF_LLM_MAX_TOKENS`、queue polling は `WEREWOLF_ADVANCE_JOB_POLL_INTERVAL_SECONDS` / `WEREWOLF_ADVANCE_JOB_POLL_TIMEOUT_SECONDS`、trace retention は `WEREWOLF_LLM_TRACE_RETENTION_DAYS` で制御します。

## DB

- Supabase が永続化の正本
- 画面から変更する game、参加者、履歴、private observation、operation request、LLM trace、audit は DB に保存する
- 運用だけで変更する設定値、definition、UI text、CSS、screen 配置は settings / resource file に保存する
- `public` schema は RLS を有効化し、CLI / Streamlit が Data API から触る最小 table だけを expose する
- `private` schema は worker 専用で、private state と private event stream を public API / Data API へ出さない
- manual player token は作成時だけ平文で返し、DB には hash だけを保存する
- 外部公開の履歴は `game_public_turns` と `game_summaries` に統一する

Migration:

```bash
supabase migration up
```

## テスト

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
```

配置方針:

- ルール、勝敗、投票、夜行動: `tests/unit/domain/`
- LLM observation / decision: `tests/unit/domain/test_langchain_llm.py`
- usecase workflow と境界: `tests/unit/usecase/`
- import 境界と公開面: `tests/unit/architecture/`
- CLI / Streamlit / client adapter: `tests/unit/interface/`
- FastAPI health: `tests/integration/api/`

## 生成物

Git 管理しない runtime 生成物は、原則として `.werewolf-agent/` または `%TEMP%\werewolf-agent` に集約します。

- operational logs: `.werewolf-agent/logs/werewolf-agent.jsonl`
- Supabase session file: OS user profile 側の app config directory
- Streamlit active game selection: 現在の Streamlit session 内だけに保持する
- pytest / ruff / mypy cache: `.werewolf-agent/cache/`
- pytest tmp: `.werewolf-agent/cache/pytest/tmp/`
- coverage data: `.werewolf-agent/coverage/.coverage`
- public timeline JSONL logs

## Docs

HTML を確認する場合:

```bash
uv run --group docs --extra api --extra streamlit sphinx-build -b html -c docs/sphinx docs docs/sphinx/_build/html
```

`docs/sphinx/_build` は生成物です。正本 docs として編集しません。

## 未実装

- 実 provider の長時間 QA と evaluation workflow
- 複数 manual player
- React UI

## Handoff

中断時はこれだけ残します。

```markdown
## Handoff

- 目的:
- 完了:
- 未完了:
- 実行したコマンド:
- 次に見るファイル:
- 判断が必要なこと:
```
