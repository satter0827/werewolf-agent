# Development

途中参加者が最短で再開するためのメモです。

## 現在地

- backend 中心
- deterministic domain core 実装済み
- `usecase` は interface と domain の唯一の接続点
- Django API は game 作成、状態取得、step 進行、public event 取得まで実装済み
- CLI `play` は公開 HTTP API だけで 1 game を完走できる
- 実 LLM provider、human action、private observation、観戦 UI は未実装

## 最初に実行

```bash
uv sync --group dev --extra api
uv run werewolf-agent doctor
uv run pytest
uv run --extra api python backend/manage.py check
```

API を起動:

```bash
uv run --extra api python backend/manage.py migrate
uv run --extra api python backend/manage.py runserver
```

CLI で確認:

```bash
uv run werewolf-agent play --api-url http://127.0.0.1:8000/api --players 6 --seed 1
```

## 配置

| Path | 責務 |
| --- | --- |
| `backend/src/werewolf_agent/commons/configuration/` | `.env` / 環境変数、既定値 |
| `backend/src/werewolf_agent/domain/models.py` | headless 利用者が扱う `Player` / `Action` / snapshot / observation / event |
| `backend/src/werewolf_agent/domain/service.py` | snapshot と pending action を受け取る stateless domain 関数 |
| `backend/src/werewolf_agent/domain/rules/` | domain 内部 rules |
| `backend/src/werewolf_agent/usecase/jobs/` | stateless job、業務 validation、repository port、domain 接続 |
| `backend/src/werewolf_agent/contracts/schemas.py` | 公開 HTTP API DTO、Problem Details |
| `backend/src/werewolf_agent/contracts/` | error code、safe exception、Problem Details |
| `backend/src/werewolf_agent/interfaces/api/` | Django API、HTTP 入出力、Django config、例外変換 |
| `backend/src/werewolf_agent/interfaces/application/` | usecase adapter、DB repository、transaction、依存注入 |
| `backend/src/werewolf_agent/interfaces/cli/` | Typer CLI と HTTP client |
| `backend/src/werewolf_agent/interfaces/shared/` | interface runtime helper |
| `backend/src/werewolf_agent/commons/` | logging、events、redaction |
| `tests/unit/` | process 内 unit test |
| `tests/integration/api/` | Django / DB / API integration test |

## 境界

- CLI は `contracts.schemas` と HTTP client だけを使う
- `interfaces/api` と `interfaces/cli` は domain / usecase を直接 import しない
- interface 層から usecase を呼ぶ場所は `interfaces/application` に限定する
- `interfaces/application` は `werewolf_agent.usecase.jobs` の top-level 公開面だけを import する
- `commons.configuration` は interface から読み込む設定境界として扱い、domain / usecase から import しない
- usecase から domain へ入る code は `usecase/jobs` 配下に限定し、`domain.models` と `domain.service` だけを import する
- 業務要件は usecase、コアルールは domain、HTTP / CLI / 画面向け変換は interface に置く
- domain は usecase / interfaces / config / commons / llm を import しない
- domain の公開 model は `Player`、`Action`、`GameSnapshot`、`Observation` のような headless 利用単位を優先する
- API は `private_state` を保存してよいが public response へ出さない
- public event に role、night action、secret、token、API key を混ぜない

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
- CLI の public API 境界: `tests/unit/interfaces/cli/`
- Django / DB / endpoint: `tests/integration/api/`
- 実 LLM provider 接続: 通常 unit test から分離する

## 生成物

Git 管理しないものは `.werewolf-agent/` に集約します。

- SQLite: `.werewolf-agent/db/db.sqlite3`
- pytest / ruff / mypy cache
- coverage data
- JSONL logs
- collectstatic output

`.werewolf-agent/.gitkeep` 以外はコミットしません。

## Optional Dependencies

```bash
uv sync --group dev --extra api
uv sync --group dev --extra llm
```

- `api`: Django / DRF / DB / gunicorn
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

wheel から API 管理コマンドを使う場合:

```bash
uv run --with "dist/werewolf_agent-0.1.0-py3-none-any.whl[api]" --no-project -- werewolf-agent-api-manage check
```

本番相当:

- `WEREWOLF_DJANGO_DEBUG=false`
- 強い `WEREWOLF_DJANGO_SECRET_KEY`
- 公開 host に合わせた `WEREWOLF_DJANGO_ALLOWED_HOSTS`
- migration は release command / one-off job で実行

## 未実装

- LLM provider adapter
- structured output parser / validator
- human / external agent action API
- private observation 認証
- SSE / WebSocket / UI
- replay / evaluation workflow

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
