# Werewolf Agent

LLM agent を人狼ゲームのプレイヤーとして動かす Python backend です。
deterministic domain core がゲームの真実を管理し、外側には public state と public timeline だけを返します。

## 現在地

- FastAPI / CLI / Streamlit から、LLM 同士の game と 1 人 manual player 混在 game を決着まで進められる
- LangChain `fake` provider、LM Studio、OpenAI provider を設定値で切り替えられる
- role、rule、scenario、LLM player、prompt、fake response、Streamlit i18n は runtime definition として読み込む
- 公開 API は `health`、`setup-options`、`games`、`advance`、`timeline`、`reveal`、`player observation`、`player action` に絞る
- manual player の token は作成レスポンスで 1 回だけ返し、保存・public response・public timeline・運用ログへ出さない

## 起動

```bash
uv sync --group dev --extra api --extra llm --extra streamlit
uv run werewolf-agent doctor
uv run --extra api alembic upgrade head
uv run --extra api uvicorn werewolf_agent.interface.api.app:create_app --factory
```

別ターミナルで CLI から game を実行します。

```bash
uv run werewolf-agent play --api-url http://127.0.0.1:8000/api/v1 --role-count werewolf=1 --role-count seer=1 --role-count knight=1 --role-count villager=3 --seed 1
uv run werewolf-agent play --api-url http://127.0.0.1:8000/api/v1 --role-count werewolf=1 --role-count seer=1 --role-count knight=1 --role-count villager=3 --seed 1 --manual-player player-1
```

公開履歴を確認する場合:

```bash
uv run werewolf-agent setup-options --api-url http://127.0.0.1:8000/api/v1
uv run werewolf-agent games --api-url http://127.0.0.1:8000/api/v1
uv run werewolf-agent timeline <game_id> --api-url http://127.0.0.1:8000/api/v1 --follow
uv run werewolf-agent replay --timeline .werewolf-agent/logs/game-001.jsonl
```

Streamlit:

```bash
uv run --extra streamlit streamlit run backend/src/werewolf_agent/interface/entrypoint/streamlit/app.py
```

VS Code では `App: API + Streamlit` を使います。OneDrive / sandbox の権限差分を避けるため、検証用 SQLite と Streamlit save は `%TEMP%\werewolf-agent` 配下、運用ログは `.werewolf-agent/logs` 配下へ置きます。

## LLM Provider

既定は外部 API を使わない `fake` provider です。

```text
WEREWOLF_LLM_PROVIDER=fake
WEREWOLF_MODEL=fake-list-llm
```

LM Studio:

```text
WEREWOLF_LLM_PROVIDER=lmstudio
WEREWOLF_MODEL=<LM Studio model identifier>
WEREWOLF_LLM_BASE_URL=http://host.docker.internal:1234/v1
```

OpenAI:

```text
WEREWOLF_LLM_PROVIDER=openai
WEREWOLF_MODEL=gpt-4.1-mini
WEREWOLF_LLM_BASE_URL=
OPENAI_API_KEY=<secret>
```

LLM には `AgentObservation` だけを渡します。観測には `available_actions`、action ごとの `legal_targets`、公開 speech / vote history を含め、role、夜行動 target、private state、raw prompt、raw provider response、API key は保存・公開・ログ出力しません。

## API

| Method | Path | 用途 |
| --- | --- | --- |
| `GET` | `/api/v1/health` | health check |
| `GET` | `/api/v1/setup-options` | game 作成用 metadata |
| `POST` | `/api/v1/games` | game 作成 |
| `GET` | `/api/v1/games` | game 一覧 |
| `GET` | `/api/v1/games/{game_id}` | public state |
| `POST` | `/api/v1/games/{game_id}/advance` | 1 step 進行 |
| `GET` | `/api/v1/games/{game_id}/timeline` | public timeline |
| `GET` | `/api/v1/games/{game_id}/reveal` | observer / demo 用 reveal |
| `GET` | `/api/v1/games/{game_id}/players/{player_id}/observation` | Bearer token 付き private observation |
| `POST` | `/api/v1/games/{game_id}/players/{player_id}/actions` | Bearer token 付き manual action |

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
| `backend/src/werewolf_agent/interface/application/` | transaction、repository adapter、依存注入、wire schema 変換 |
| `backend/src/werewolf_agent/interface/api/` | FastAPI router |
| `backend/src/werewolf_agent/interface/entrypoint/cui/` | public HTTP API だけを呼ぶ CLI |
| `backend/src/werewolf_agent/interface/entrypoint/streamlit/` | Streamlit 画面、状態、表示 model |
| `backend/src/werewolf_agent/interface/shared/` | HTTP client、request builder、HTTP 例外変換 |
| `backend/src/werewolf_agent/contracts/` | Pydantic 外部契約、error code、Problem Details |
| `backend/src/werewolf_agent/commons/` | 副作用のない共通値、validation、redaction |

## 設定とログ

設定 default は `backend/src/werewolf_agent/resources/settings/defaults.toml` が正です。`.env.example` は override 例だけを置きます。

`interface/runtime` が設定、definition TOML、logging bootstrap を浅い入口で解決し、`interface/application` から usecase へ値として注入します。domain と usecase は source path、packaged fallback、`.env`、logging 設定を知りません。

運用ログは JSON Lines です。既定出力先は `.werewolf-agent/logs/werewolf-agent.jsonl` です。script、VS Code、Docker Compose は `.werewolf-agent/logs` を使い、API は `api.jsonl`、Streamlit は `streamlit.jsonl`、CLI は `cli.jsonl`、migration は `migrate.jsonl` に出します。

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
uv run --group docs --extra api --extra streamlit sphinx-build -b html -c docs/sphinx docs docs/sphinx/_build/html
```

## 未実装

- 実 provider の長時間 QA と evaluation workflow
- 複数 manual player
- 永続 login / session
- React UI

## License

MIT License
