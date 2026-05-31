# Development

途中参加者が最短で再開するための作業メモです。
完成版の設計書は `docs/design/`、Sphinx の入口と設定は `docs/sphinx/` に置きます。

## 現在地

- deterministic domain core 実装済み
- game rules / game roles / LLM players / prompt / fake responses は `interface/runtime` の共通 loader で読み込む
- `GameUseCases` facade 経由で game 作成、一覧、状態取得、進行、次入力待ちまでの進行、timeline、private observation、manual action を扱う
- FastAPI の公開面は `/health`、`/ruleset`、`/games`、`/advance`、`/advance-until-input`、`/timeline`、manual player endpoint に絞った
- CLI `doctor` / `ruleset` / `new` / `show` / `advance` / `play` / `timeline` / `replay` / `runs` は HTTP API だけを使う
- Streamlit は public API 経由で 1 人の human player が遊べる画面として実装済み
- Streamlit は `resources/streamlit/i18n.toml` を既定の UI 文言定義体として使い、`WEREWOLF_STREAMLIT_I18N_FILE` で差し替えられる
- 現在の LLM provider は LangChain `fake`
- 実 LLM provider、複数 human player、React UI は未実装

## 最初に実行

```bash
uv sync --group dev --extra api --extra streamlit
uv run werewolf-agent doctor
uv run pytest
uv run --extra api alembic upgrade head
```

API を起動:

```bash
uv run --extra api uvicorn werewolf_agent.interface.api.app:create_app --factory
```

CLI で確認:

```bash
uv run werewolf-agent play --api-url http://127.0.0.1:8000/api/v1 --role-count werewolf=1 --role-count seer=1 --role-count knight=1 --role-count villager=3 --seed 1
uv run werewolf-agent play --api-url http://127.0.0.1:8000/api/v1 --role-count werewolf=1 --role-count seer=1 --role-count knight=1 --role-count villager=3 --seed 1 --human-player player-1
uv run werewolf-agent runs --api-url http://127.0.0.1:8000/api/v1
uv run werewolf-agent timeline <game_id> --api-url http://127.0.0.1:8000/api/v1 --follow
```

Streamlit:

```bash
uv run --extra streamlit streamlit run backend/src/werewolf_agent/interface/entrypoint/streamlit/app.py
```

## Windows / OneDrive / Codex

この repository は OneDrive の reparse point 配下で作業されることがあります。Codex の sandbox から repository 配下へ新規生成物を書くと、`Access is denied`、Ruff cache warning、SQLite `disk I/O error` が出る場合があります。

AI が検証や browser QA を行う場合は、cache、SQLite、Streamlit save、screenshot を `%TEMP%\werewolf-agent` 配下へ置きます。運用ログだけは `.werewolf-agent/logs` 配下へ統一します。依存関係が同期済みなら `uv run --no-sync ...` を優先し、Ruff は `--no-cache`、mypy は `--no-incremental` または `%TEMP%` の cache を使います。

検証をまとめて実行する場合:

```bat
scripts\check-all.cmd --api --keep-going
```

API を一時 DB で起動する場合:

```bat
scripts\run-api.cmd --temp-state --reload
```

VS Code の Run and Debug は SQLite と Streamlit save を `%TEMP%\werewolf-agent` 配下へ向けます。運用ログは `.werewolf-agent/logs` 配下へ出し、API は `api.jsonl`、Streamlit は `streamlit.jsonl`、CLI は `cli.jsonl`、migration は `migrate.jsonl` を使います。

## 配置

| Path | 責務 |
| --- | --- |
| `backend/src/werewolf_agent/domain/game/` | ルール、状態、観測、勝敗、game event |
| `backend/src/werewolf_agent/domain/llm/` | provider 非依存 DTO、LangChain fake provider |
| `backend/src/werewolf_agent/resources/` | packaged defaults、game / LLM definition、prompt、FakeListLLM response fixture |
| `backend/src/werewolf_agent/usecase/jobs/` | `GameUseCases` facade、command、repository / telemetry port |
| `backend/src/werewolf_agent/usecase/internal/` | workflow、projection、agent adapter、唯一の domain 接点 |
| `backend/src/werewolf_agent/interface/runtime/` | settings、definition TOML loader、logging bootstrap、structlog context |
| `backend/src/werewolf_agent/interface/application/` | transaction、SQLAlchemy repository、依存注入、wire schema 変換 |
| `backend/src/werewolf_agent/interface/api/` | FastAPI app、router、SSE |
| `backend/src/werewolf_agent/interface/entrypoint/cui/` | Typer CLI、入力、表示 |
| `backend/src/werewolf_agent/interface/entrypoint/streamlit/` | Streamlit 画面、画面状態、表示 model |
| `backend/src/werewolf_agent/interface/shared/` | HTTP client、request builder、diagnostics、HTTP 例外変換、event sink |
| `backend/src/werewolf_agent/contracts/` | Pydantic 外部契約、error code、safe exception、Problem Details |
| `backend/src/werewolf_agent/commons/` | constants、messages、validation、definition value、redaction |
| `tests/unit/` | process 内 unit test |
| `tests/integration/api/` | FastAPI / DB / API integration test |

## Docs

| Path | 役割 |
| --- | --- |
| `docs/design/` | Sphinx で読む完成版の設計書 |
| `docs/notes/` | 修正の積み重ね、再開メモ、handoff |
| `docs/sphinx/` | Sphinx の設定、入口、軽い CSS |
| `docs/reference/` | autodoc API reference |

HTML を確認する場合:

```bash
uv run --group docs --extra api --extra streamlit sphinx-build -b html -c docs/sphinx docs docs/sphinx/_build/html
```

## 境界

- CLI は `contracts/schemas.py` と `GameApiClient` だけを使う
- `interface/api` と `interface/entrypoint/cui` は domain / usecase を直接 import しない
- interface 層から usecase を呼ぶ場所は `interface/application` に限定する
- 設定読み込み、ログ bootstrap、structlog context は `interface/runtime` に置く
- `interface/application` は `werewolf_agent.usecase.jobs` の top-level 公開面だけを import する
- `usecase/jobs` は domain を import せず、facade、command / query、repository / telemetry port、application bridge が必要とする永続化 contract に限定する
- usecase から domain へ入る code は `usecase/internal` 配下に限定する
- `usecase/internal` は interface / wire schema に依存させない
- `domain.game` と `domain.llm` は互いに import しない
- domain から `commons` を使う場合は副作用のない `commons.shared.messages` / `commons.shared.validation` / `commons.shared.models` / `commons.shared.definitions` だけに限定する
- public response / public timeline / operational log に role、night action target、secret、token、API key を混ぜない

## 定義体

運用で差し替える単位は次に絞ります。UI 入力や game run ごとの入力値は定義体にしません。

| 定義体 | 既定 | override | 渡す先 |
| --- | --- | --- | --- |
| ルール定義体 | `backend/src/werewolf_agent/resources/game/rules.toml` | `WEREWOLF_GAME_RULES_FILE` | `domain.game` |
| ロール定義体 | `backend/src/werewolf_agent/resources/game/roles.toml` | `WEREWOLF_GAME_ROLES_FILE` | `domain.game` |
| Player 定義体 | `backend/src/werewolf_agent/resources/llm/players.toml` | `WEREWOLF_LLM_PLAYERS_FILE` | `domain.llm` |
| Prompt 定義体 | `backend/src/werewolf_agent/resources/prompts/agent_decision.toml` | `WEREWOLF_LLM_PROMPT_FILE` | `domain.llm` |
| Fake response 定義体 | `backend/src/werewolf_agent/resources/llm/fake_responses.toml` | `WEREWOLF_LLM_FAKE_RESPONSES_FILE` | `domain.llm` |
| Streamlit i18n 定義体 | `backend/src/werewolf_agent/resources/streamlit/i18n.toml` | `WEREWOLF_STREAMLIT_I18N_FILE` | `interface/entrypoint/streamlit` |

game 用定義体、LLM 用定義体、UI 文言定義体は混在させません。`interface/runtime` が path 解決、packaged default、外部 TOML 読み込み、Pydantic 検証を共通処理で行い、`AppSettings` 構築時に定義体も検証します。`interface/application` は読み込まれた値だけを usecase へ注入します。`usecase/internal/definitions.py` は converter だけを持ち、domain / usecase には source path や definition id を持ち込みません。game 作成時は `role_counts` から人数を導出し、human seat は `human_player_id` で指定します。CLI の `--role-count` 省略時だけ `interface/entrypoint/cui` が runtime settings / role 定義体から既定構成を選びます。

## DB

DB は設定値で選びます。

- `WEREWOLF_DATABASE_URL` が空なら SQLite
- SQLite の既定値は `.werewolf-agent/db/db.sqlite3`
- SQLite の場所は `WEREWOLF_SQLITE_PATH` で変更できる
- Postgres などは `WEREWOLF_DATABASE_URL` を設定する
- usecase の保存単位は `game_runs`、`game_events`、`game_run_summaries`、`game_turns`
- 外部公開の履歴は `GameTimelineItem` だけに統一する
- human player の control token は作成時だけ平文で返し、DB には hash だけを保存する
- API の表示名、version、debug、CORS は `WEREWOLF_API_TITLE`、`WEREWOLF_API_VERSION`、`WEREWOLF_API_DEBUG`、`WEREWOLF_CORS_ALLOWED_*` で変更できる

Migration:

```bash
uv run --extra api alembic upgrade head
```

## テスト

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy backend/src
uv run --extra api pytest tests/integration/api
uv run --no-sync ruff check --no-cache --select D --ignore D100,D104 backend/src/werewolf_agent
```

配置方針:

- ルール、勝敗、投票、夜行動: `tests/unit/domain/`
- 業務 workflow と usecase 境界: `tests/unit/usecase/`
- 境界 import: `tests/unit/architecture/`
- CLI の public API 境界: `tests/unit/interface/entrypoint/cui/`
- FastAPI / DB / endpoint: `tests/integration/api/`
- 実 LLM provider 接続: 通常 unit test から分離する

## 生成物

Git 管理しない runtime 生成物は、原則として `.werewolf-agent/` または `%TEMP%\werewolf-agent` に集約します。

- SQLite: `.werewolf-agent/db/db.sqlite3`
- operational logs: `.werewolf-agent/logs/werewolf-agent.jsonl`
- Streamlit save: game metadata だけを保存し、`control_token` は現在の Streamlit session 内だけに保持する
- pytest / ruff / mypy cache: `.werewolf-agent/cache/`
- pytest tmp: `.werewolf-agent/cache/pytest/tmp/`
- coverage data: `.werewolf-agent/coverage/.coverage`
- public timeline JSONL logs

`.werewolf-agent/` は Git 管理しません。トップレベルの `.gitkeep` だけを置きます。

## Optional Dependencies

```bash
uv sync --group dev --extra api
uv sync --group dev --extra llm
uv sync --group dev --extra streamlit
```

- `api`: FastAPI / SQLAlchemy / Alembic / Uvicorn / SSE / Postgres driver
- `llm`: LangChain / OpenAI compatible provider 用。adapter は未実装
- `streamlit`: Streamlit のプレイ画面用。API は別 process で起動する

## Docker

```bash
docker compose build
docker compose run --rm migrate
docker compose up api
docker compose run --rm test
```

Postgres:

```bash
docker compose -f compose.yaml -f compose.postgres.yaml run --rm migrate
docker compose -f compose.yaml -f compose.postgres.yaml up api
docker compose -f compose.yaml -f compose.postgres.yaml run --rm test
```

## 未実装

- real LLM provider adapter
- structured output parser / validator
- 複数 human player
- external agent action API
- React UI
- evaluation workflow

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
