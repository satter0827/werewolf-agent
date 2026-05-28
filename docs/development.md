# Development

途中参加者が最短で再開するためのメモです。

## 現在地

- backend 中心
- deterministic domain core 実装済み
- `usecase.jobs` は interface と domain の唯一の接続点
- FastAPI は game 作成、一覧、状態取得、step 進行、public event、turn history、public SSE まで実装済み
- CLI `play` / `watch` / `replay` / `runs` / `turns` は公開 HTTP API だけを使う
- 現在の LLM provider は `fake_llm`。実 LLM provider、human action、private observation、Streamlit / React UI は未実装

## 最初に実行

```bash
uv sync --group dev --extra api
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
uv run werewolf-agent play --api-url http://127.0.0.1:8000/api/v1 --players 6 --seed 1
uv run werewolf-agent runs --api-url http://127.0.0.1:8000/api/v1
uv run werewolf-agent watch <game_id> --api-url http://127.0.0.1:8000/api/v1
```

## 配置

| Path | 責務 |
| --- | --- |
| `backend/src/werewolf_agent/__main__.py` | `python -m werewolf_agent` の薄い CLI 委譲 |
| `backend/src/werewolf_agent/domain/game/models.py` | headless game が扱う `Player` / `Action` / snapshot / observation / event |
| `backend/src/werewolf_agent/domain/game/service.py` | snapshot と pending action を受け取る stateless game 関数 |
| `backend/src/werewolf_agent/domain/game/rules/` | game 内部 rules |
| `backend/src/werewolf_agent/domain/llm/models.py` | provider 非依存の agent observation / decision DTO |
| `backend/src/werewolf_agent/domain/llm/service.py` | FakeLLM decision logic |
| `backend/src/werewolf_agent/domain/llm/ports.py` | 将来の LLM provider adapter port |
| `backend/src/werewolf_agent/usecase/jobs/` | stateless job、業務 validation、repository port、domain 接続 |
| `backend/src/werewolf_agent/interface/api/` | FastAPI app、router、例外変換、SSE |
| `backend/src/werewolf_agent/interface/application/` | usecase adapter、SQLAlchemy repository、transaction、依存注入、Alembic migration |
| `backend/src/werewolf_agent/interface/entrypoint/cui/` | Typer CLI と HTTP client |
| `backend/src/werewolf_agent/interface/shared/` | settings、logging、wire schema、runtime helper |
| `backend/src/werewolf_agent/interface/entrypoint/streamlit/` | 将来の Streamlit 入口 |
| `backend/src/werewolf_agent/contracts/` | safe exception |
| `backend/src/werewolf_agent/commons/` | error code、message catalog、validation、event sink、redaction |
| `tests/unit/` | process 内 unit test |
| `tests/integration/api/` | FastAPI / DB / API integration test |

## 境界

- CLI は `interface/shared/schemas.py` と HTTP client だけを使う
- `interface/api` と `interface/entrypoint/cui` は domain / usecase を直接 import しない
- interface 層から usecase を呼ぶ場所は `interface/application` に限定する
- 設定と logging は `interface/shared` に置き、domain / usecase には注入済み値だけ渡す
- `interface/application` は `werewolf_agent.usecase.jobs` の top-level 公開面だけを import する
- usecase から domain へ入る code は `usecase/jobs` 配下に限定し、`domain.game.*` と `domain.llm.*` の公開面だけを import する
- `domain.game` と `domain.llm` は互いに import せず、observation / decision / action の変換は usecase に置く
- 業務要件は usecase、コアルールは domain、HTTP / CLI / 画面向け変換は interface に置く
- domain から `commons` を使う場合は副作用のない `commons.shared.messages` / `commons.shared.validation` だけに限定する
- domain の公開 model は `Player`、`Action`、`GameSnapshot`、`Observation` のような headless 利用単位を優先する
- API は `private_state` を保存してよいが public response へ出さない
- public event に role、night action、secret、token、API key を混ぜない

## DB

DB は設定値で選びます。

- `WEREWOLF_DATABASE_URL` が空なら SQLite
- SQLite の既定値は `.werewolf-agent/db/db.sqlite3`
- SQLite の場所は `WEREWOLF_SQLITE_PATH` で変更できる
- Postgres などは `WEREWOLF_DATABASE_URL` を設定する
- usecase の保存単位は `game_runs`、`game_events`、`game_run_summaries`、`game_turns`
- `game_run_summaries` と `game_turns` は CLI と将来 UI 用の public read model
- ruleset metadata の説明文、role 表示名、phase 表示名は `WEREWOLF_GAME_RULESET_DESCRIPTION_TEMPLATE`、`WEREWOLF_GAME_ROLE_NAMES`、`WEREWOLF_GAME_PHASE_NAMES` で変更できる
- agent type は `llm`。実 provider は `WEREWOLF_LLM_PROVIDER=fake_llm` で切り替える
- API の表示名、version、debug、CORS は `WEREWOLF_API_TITLE`、`WEREWOLF_API_VERSION`、`WEREWOLF_API_DEBUG`、`WEREWOLF_CORS_ALLOWED_*` で変更できる
- コード上の `WEREWOLF_API_DEBUG` 既定値は `false`。ローカル開発用の `.env.example` と `compose.yaml` は `true` を明示する

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
```

配置方針:

- ルール、勝敗、投票、夜行動: `tests/unit/domain/`
- 業務 workflow と usecase 境界: `tests/unit/usecase/`
- 境界 import: `tests/unit/architecture/`
- CLI の public API 境界: `tests/unit/interface/entrypoint/cui/`
- FastAPI / DB / endpoint: `tests/integration/api/`
- 実 LLM provider 接続: 通常 unit test から分離する

## 生成物

Git 管理しないものは `.werewolf-agent/` に集約します。

- SQLite: `.werewolf-agent/db/db.sqlite3`
- pytest / ruff / mypy cache: `.werewolf-agent/cache/`
- pytest tmp: `.werewolf-agent/cache/pytest/tmp/`
- coverage data: `.werewolf-agent/coverage/.coverage`
- JSONL logs

`.werewolf-agent/` は Git 管理しません。トップレベルの `.gitkeep` だけを置きます。

## Optional Dependencies

```bash
uv sync --group dev --extra api
uv sync --group dev --extra llm
```

- `api`: FastAPI / SQLAlchemy / Alembic / Uvicorn / SSE / Postgres driver
- `llm`: LangChain / OpenAI compatible provider 用。adapter は未実装

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

## 配布

```bash
uv build --no-sources
```

本番相当:

- `WEREWOLF_API_DEBUG=false`
- `WEREWOLF_DATABASE_URL` または永続 volume 上の `WEREWOLF_SQLITE_PATH`
- 公開 UI に合わせた `WEREWOLF_CORS_ALLOWED_ORIGINS`
- migration は release command / one-off job で実行

## 未実装

- real LLM provider adapter
- structured output parser / validator
- human / external agent action API
- private observation 認証
- Streamlit / React UI
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
