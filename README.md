# Werewolf Agent

LLM agent を人狼ゲームのプレイヤーとして動かす Python backend です。
ゲームの真実は deterministic domain core が持ち、外側には公開状態と public timeline だけを出します。

## 現在地

- 5〜8 人の同期ゲームを FastAPI 経由で作成、進行、一覧、再生できる
- 役職は `villager`、`werewolf`、`seer`、`knight`
- フェーズは `night`、`day_discussion`、`voting`、`finished`
- LangChain `FakeListLLM` provider で 1 game を CLI から完走できる
- CLI は `doctor`、`ruleset`、`new`、`show`、`advance`、`play`、`timeline`、`replay`、`runs` を持つ
- 1 game につき 1 人の `human` player を CLI / Streamlit から操作できる
- 実 LLM provider、複数 human player、React UI は未実装

## 起動

```bash
uv sync --group dev --extra api --extra streamlit
uv run werewolf-agent doctor
uv run --extra api alembic upgrade head
uv run --extra api uvicorn werewolf_agent.interface.api.app:create_app --factory
```

別ターミナルで 1 game を実行します。

```bash
uv run werewolf-agent play --api-url http://127.0.0.1:8000/api/v1 --players 6 --seed 1
```

手動 player を含む game を作る場合:

```bash
uv run werewolf-agent new --api-url http://127.0.0.1:8000/api/v1 --human-player player-1 --players 6 --seed 1
uv run werewolf-agent show <game_id> --api-url http://127.0.0.1:8000/api/v1
uv run werewolf-agent advance <game_id> --api-url http://127.0.0.1:8000/api/v1
```

公開 timeline を確認、保存、再生する場合:

```bash
uv run werewolf-agent runs --api-url http://127.0.0.1:8000/api/v1
uv run werewolf-agent timeline <game_id> --api-url http://127.0.0.1:8000/api/v1 --follow
uv run werewolf-agent play --api-url http://127.0.0.1:8000/api/v1 --players 6 --seed 1 --log-jsonl .werewolf-agent/logs/game-001.jsonl
uv run werewolf-agent replay --timeline .werewolf-agent/logs/game-001.jsonl
```

Streamlit のプレイ画面:

```bash
uv run --extra streamlit streamlit run backend/src/werewolf_agent/interface/entrypoint/streamlit/app.py
```

VS Code では `App: API + Streamlit` を選択します。OneDrive / sandbox の権限差分を避けるため、SQLite と Streamlit 保存データは `%TEMP%\werewolf-agent` 配下へ置き、運用ログだけ `.werewolf-agent/logs` 配下へ出します。

## API

公開 HTTP API は次だけです。

| Method | Path | 用途 |
| --- | --- | --- |
| `GET` | `/api/v1/health` | health check |
| `GET` | `/api/v1/ruleset` | 既定 ruleset metadata |
| `POST` | `/api/v1/games` | game run 作成 |
| `GET` | `/api/v1/games` | game run 一覧 |
| `GET` | `/api/v1/games/{game_id}` | 公開状態取得 |
| `POST` | `/api/v1/games/{game_id}/advance` | 1 usecase step 進行 |
| `GET` | `/api/v1/games/{game_id}/timeline` | 公開 timeline 取得 |
| `GET` | `/api/v1/games/{game_id}/timeline/stream` | 公開 timeline SSE |
| `GET` | `/api/v1/games/{game_id}/players/{player_id}/observation` | private observation 取得 |
| `POST` | `/api/v1/games/{game_id}/players/{player_id}/actions` | manual action 投稿 |

詳細は [docs/design/api.md](docs/design/api.md) を参照してください。

## 構成

| Path | 責務 |
| --- | --- |
| `backend/src/werewolf_agent/domain/game/` | ルール、状態、観測、勝敗、game event |
| `backend/src/werewolf_agent/domain/llm/` | provider 非依存の agent 観測 DTO、意思決定 DTO、LangChain provider、prompt loader |
| `backend/src/werewolf_agent/usecase/jobs/` | interface 向けの薄い `GameUseCases` facade、公開 DTO、repository / telemetry port |
| `backend/src/werewolf_agent/usecase/internal/` | usecase 実処理、projection、唯一の domain 接点 |
| `backend/src/werewolf_agent/interface/runtime/` | settings、logging bootstrap、structlog context |
| `backend/src/werewolf_agent/interface/application/` | transaction、SQLAlchemy repository、依存注入、wire schema 変換 |
| `backend/src/werewolf_agent/interface/api/` | FastAPI、HTTP 入出力、SSE |
| `backend/src/werewolf_agent/interface/entrypoint/cui/` | Typer CLI、public HTTP client 利用、表示 |
| `backend/src/werewolf_agent/interface/entrypoint/streamlit/` | Streamlit 画面、画面状態、表示 model |
| `backend/src/werewolf_agent/interface/shared/` | HTTP client、request builder、diagnostics、HTTP 例外変換、event sink |
| `backend/src/werewolf_agent/contracts/` | Pydantic 外部契約、error code、safe exception、Problem Details |
| `backend/src/werewolf_agent/commons/` | 副作用のない constants、messages、validation、redaction |

## 設定とログ

設定 default は `backend/src/werewolf_agent/resources/settings/defaults.toml` が正です。`.env.example` は override 用の雛形であり、既定値の二重管理には使いません。

`interface/runtime` が `defaults.toml`、`.env`、環境変数を読み取り、API / CLI / Streamlit の浅い場所で usecase へ依存として注入します。DB は `WEREWOLF_DATABASE_URL` が空なら `WEREWOLF_SQLITE_PATH` の SQLite を使います。

運用ログは ECS 風 field の JSON Lines です。既定出力先は `.werewolf-agent/logs/werewolf-agent.jsonl` です。script、VS Code、Docker Compose は `.werewolf-agent/logs` を使い、API は `api.jsonl`、Streamlit は `streamlit.jsonl`、CLI は `cli.jsonl`、migration は `migrate.jsonl` に出します。public response、public timeline、operational log には role、night action target、private state、token、API key を出しません。

## 検証

```bash
scripts\check-all.cmd --api --keep-going
uv run --no-sync ruff check --no-cache --select D --ignore D100,D104 backend/src/werewolf_agent
uv run --group docs --extra api --extra streamlit sphinx-build -b html docs docs/sphinx/_build/html
```

個別に確認する場合:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy backend/src
uv run --extra api pytest tests/integration/api
```

## ドキュメント

- [docs/design/domain.md](docs/design/domain.md): domain core と境界
- [docs/design/api.md](docs/design/api.md): 公開 API 契約
- [docs/notes/development.md](docs/notes/development.md): 再開メモ、未実装、handoff
- [docs/sphinx/index.md](docs/sphinx/index.md): Sphinx 入口
- `docs/reference/`: autodoc API reference

## 次の一手

- 実 LLM provider adapter と structured output validation
- 複数 human player / external agent action API
- 永続 login/session による private observation 認証
- React UI
- evaluation workflow

## License

MIT License
