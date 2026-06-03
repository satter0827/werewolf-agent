# Development

途中参加者が最短で再開するための作業メモです。
完成版の設計は `docs/design/`、Sphinx の入口と設定は `docs/sphinx/` に置きます。

## 現在地

- deterministic domain core 実装済み
- FastAPI / CLI / Streamlit から LLM 同士の game と 1 人 manual player 混在 game を進められる
- `GameService` facade 経由で create / get / advance / list / timeline / reveal / private observation / manual action を扱う
- FastAPI の公開面は `/health`、`/setup-options`、`/games`、`/advance`、`/timeline`、`/reveal`、manual player endpoint に絞る
- CLI `doctor` / `setup-options` / `new` / `show` / `advance` / `play` / `timeline` / `replay` / `games` は HTTP API だけを使う
- Streamlit は public API 経由で Play / Observe を提供する
- LLM provider は LangChain `fake`、LM Studio、OpenAI を設定値で切り替える
- 複数 manual player、永続 login / session、React UI は未実装

## 最初に実行

```bash
uv sync --group dev --extra api --extra llm --extra streamlit
uv run werewolf-agent doctor
uv run --extra api alembic upgrade head
```

API:

```bash
uv run --extra api uvicorn werewolf_agent.interface.api.app:create_app --factory
```

CLI:

```bash
uv run werewolf-agent setup-options --api-url http://127.0.0.1:8000/api/v1
uv run werewolf-agent play --api-url http://127.0.0.1:8000/api/v1 --role-count werewolf=1 --role-count seer=1 --role-count knight=1 --role-count villager=3 --seed 1
uv run werewolf-agent play --api-url http://127.0.0.1:8000/api/v1 --role-count werewolf=1 --role-count seer=1 --role-count knight=1 --role-count villager=3 --seed 1 --manual-player player-1
uv run werewolf-agent games --api-url http://127.0.0.1:8000/api/v1
uv run werewolf-agent timeline <game_id> --api-url http://127.0.0.1:8000/api/v1 --follow
```

Streamlit:

```bash
uv run --extra streamlit streamlit run backend/src/werewolf_agent/interface/entrypoint/streamlit/app.py
```

## Windows / OneDrive / Codex

この repository は OneDrive の reparse point 配下で作業されることがあります。Codex の sandbox から repository 配下へ新規生成物を書くと、`Access is denied`、Ruff cache warning、SQLite `disk I/O error` が出る場合があります。

検証用 cache、SQLite、Streamlit save、browser QA screenshot は `%TEMP%\werewolf-agent` 配下へ置きます。運用ログだけは `.werewolf-agent/logs` 配下へ統一します。依存関係が同期済みなら `uv run --no-sync ...` を優先し、Ruff は `--no-cache`、mypy は `--no-incremental` または `%TEMP%` の cache を使います。

まとめて検証:

```bat
scripts\check-all.cmd --api --keep-going
```

API を一時 DB で起動:

```bat
scripts\run-api.cmd --temp-state --reload
```

VS Code の Run and Debug は SQLite と Streamlit save を `%TEMP%\werewolf-agent` 配下へ向けます。運用ログは `.werewolf-agent/logs` 配下へ出し、API は `api.jsonl`、Streamlit は `streamlit.jsonl`、CLI は `cli.jsonl`、migration は `migrate.jsonl` を使います。

## 配置

| Path | 責務 |
| --- | --- |
| `backend/src/werewolf_agent/domain/game/` | ルール、状態、観測、勝敗、game event |
| `backend/src/werewolf_agent/domain/llm/` | provider 非依存 DTO、LangChain decision provider |
| `backend/src/werewolf_agent/resources/` | packaged defaults、game / LLM definition、prompt、FakeListLLM response |
| `backend/src/werewolf_agent/usecase/jobs/` | `GameService` facade、command / query、repository / telemetry port |
| `backend/src/werewolf_agent/usecase/internal/` | workflow、projection、agent adapter、唯一の domain 接点 |
| `backend/src/werewolf_agent/interface/runtime/` | settings、definition loader、logging bootstrap |
| `backend/src/werewolf_agent/interface/application/` | transaction、SQLAlchemy repository、依存注入、wire schema 変換 |
| `backend/src/werewolf_agent/interface/api/` | FastAPI app、router |
| `backend/src/werewolf_agent/interface/entrypoint/cui/` | Typer CLI、HTTP client、表示 |
| `backend/src/werewolf_agent/interface/entrypoint/streamlit/` | Streamlit 画面、画面状態、表示 model |
| `backend/src/werewolf_agent/interface/shared/` | HTTP client、request builder、HTTP 例外変換、event sink |
| `backend/src/werewolf_agent/contracts/` | Pydantic 外部契約、error code、Problem Details |
| `backend/src/werewolf_agent/commons/` | constants、messages、validation、definition value、redaction |
| `tests/unit/` | process 内 unit test |
| `tests/integration/api/` | FastAPI / DB / API integration test |

## 境界

- CLI は `contracts/schemas.py` と `GameApiClient` だけを使う
- `interface/api` と `interface/entrypoint/cui` は domain / usecase を直接 import しない
- interface 層から usecase を呼ぶ場所は `interface/application` に限定する
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

`interface/runtime` が path 解決、packaged default、外部 TOML 読み込み、Pydantic 検証を共通処理で行います。`interface/application` は読み込まれた値だけを usecase へ注入します。game 作成時は `role_counts` から人数を導出し、manual seat は `manual_player_id` で指定します。

## DB

- `WEREWOLF_DATABASE_URL` が空なら SQLite
- SQLite の既定値は `.werewolf-agent/db/db.sqlite3`
- SQLite の場所は `WEREWOLF_SQLITE_PATH` で変更できる
- usecase の保存単位は `games`、`game_events`、`game_summaries`、`game_turns`
- manual player token は作成時だけ平文で返し、DB には hash だけを保存する
- 外部公開の履歴は `GameTimelineItem` だけに統一する

Migration:

```bash
uv run --extra api alembic upgrade head
```

## テスト

```bash
uv run pytest
uv run --extra api pytest tests/integration/api
uv run ruff check .
uv run ruff format --check .
uv run mypy backend/src
uv run --no-sync ruff check --no-cache --select D --ignore D100,D104 backend/src/werewolf_agent
```

配置方針:

- ルール、勝敗、投票、夜行動: `tests/unit/domain/`
- LLM observation / decision: `tests/unit/domain/test_langchain_llm.py`
- usecase workflow と境界: `tests/unit/usecase/`
- import 境界と公開面: `tests/unit/architecture/`
- CLI / Streamlit / shared client: `tests/unit/interface/`
- FastAPI / DB / endpoint: `tests/integration/api/`

## 生成物

Git 管理しない runtime 生成物は、原則として `.werewolf-agent/` または `%TEMP%\werewolf-agent` に集約します。

- SQLite: `.werewolf-agent/db/db.sqlite3`
- operational logs: `.werewolf-agent/logs/werewolf-agent.jsonl`
- Streamlit save: game metadata だけを保存し、manual token は現在の Streamlit session 内だけに保持する
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
- 永続 login / session
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
