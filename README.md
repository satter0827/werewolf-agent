# Werewolf Agent

LLM agent を人狼ゲームのプレイヤーとして動かす Python backend です。
ゲームの真実は deterministic domain core が持ち、外側には公開状態と public event だけを出します。

## 現在地

- 5〜8 人の同期ゲームを実行できる
- 役職は `villager`、`werewolf`、`seer`、`knight`
- フェーズは `night`、`day_discussion`、`voting`、`finished`
- `fake_llm` provider で FastAPI 経由の 1 ゲームを CLI から完走できる
- API は game 作成、状態取得、一覧、1 step 進行、public event、turn history、public SSE を持つ
- CLI は `doctor`、`ruleset`、`create`、`state`、`step`、`play`、`watch`、`replay`、`runs`、`turns` を持つ
- 1 game につき 1 人の `human` player を CLI から操作できる
- 実 LLM provider、複数 human player、Streamlit / React UI は未実装

## 動かす

```bash
uv sync --group dev --extra api
uv run werewolf-agent doctor
uv run --extra api alembic upgrade head
uv run --extra api uvicorn werewolf_agent.interface.api.app:create_app --factory
```

別ターミナル:

```bash
uv run werewolf-agent play --api-url http://127.0.0.1:8000/api/v1 --players 6 --seed 1
```

`python -m` でも CLI を起動できます。

```bash
uv run python -m werewolf_agent --help
```

public event を JSONL に残す:

```bash
uv run werewolf-agent play --api-url http://127.0.0.1:8000/api/v1 --players 6 --seed 1 --log-jsonl .werewolf-agent/logs/game-001.jsonl
```

保存済み run と public timeline を確認する:

```bash
uv run werewolf-agent runs --api-url http://127.0.0.1:8000/api/v1
uv run werewolf-agent watch <game_id> --api-url http://127.0.0.1:8000/api/v1
uv run werewolf-agent replay --events .werewolf-agent/logs/game-001.jsonl
```

1 人だけ手動で操作する:

```bash
uv run werewolf-agent play --human-player player-1 --players 6 --seed 1
```

game を作成して token を控え、個別に進める:

```bash
uv run werewolf-agent create --human-player player-1 --players 6 --seed 1
uv run werewolf-agent state <game_id>
uv run werewolf-agent step <game_id>
```

## API

| Method | Path | 用途 |
| --- | --- | --- |
| `GET` | `/api/v1/health` | health check |
| `GET` | `/api/v1/rulesets/default` | MVP ruleset metadata |
| `POST` | `/api/v1/games` | game run 作成 |
| `GET` | `/api/v1/games` | game run 一覧 |
| `GET` | `/api/v1/games/{game_id}` | 公開状態取得 |
| `POST` | `/api/v1/games/{game_id}/steps` | 1 step 進行 |
| `GET` | `/api/v1/games/{game_id}/players/{player_id}/observation` | private observation 取得 |
| `POST` | `/api/v1/games/{game_id}/players/{player_id}/actions` | manual action 投稿 |
| `GET` | `/api/v1/games/{game_id}/events?after=<seq>` | public event 取得 |
| `GET` | `/api/v1/games/{game_id}/events/stream?after=<seq>` | public event SSE |
| `GET` | `/api/v1/games/{game_id}/turns?after=<seq>` | UI 向け public timeline |

詳細は [docs/api.md](docs/api.md)。

## 設計

| Path | 責務 |
| --- | --- |
| `backend/src/werewolf_agent/domain/game/` | ルール、状態、観測、勝敗、game event |
| `backend/src/werewolf_agent/domain/llm/` | provider 非依存の agent 観測 DTO、意思決定 DTO、FakeLLM decision |
| `backend/src/werewolf_agent/usecase/jobs/` | 公開 usecase facade、DTO、repository port |
| `backend/src/werewolf_agent/usecase/internal/` | usecase workflow、業務 validation、domain 接続、projection、agent adapter |
| `backend/src/werewolf_agent/interface/api/` | FastAPI、HTTP 入出力、SSE |
| `backend/src/werewolf_agent/interface/application/` | usecase adapter、SQLAlchemy repository、transaction、依存注入 |
| `backend/src/werewolf_agent/interface/entrypoint/cui/` | Typer CLI と public HTTP client |
| `backend/src/werewolf_agent/interface/shared/` | HTTP 例外変換、interface 共通 message、event sink |
| `backend/src/werewolf_agent/interface/entrypoint/streamlit/` | 将来の Streamlit 入口 |
| `backend/src/werewolf_agent/contracts/` | Pydantic 外部契約、error code、safe exception、Problem Details |
| `backend/src/werewolf_agent/commons/` | configuration、logging、message catalog、redaction、shared helper |

境界:

- `domain` は `.env`、I/O、logging 設定、LLM provider を知らない
- `domain.game` と `domain.llm` は互いに import せず、usecase が observation / decision / action を変換して接続する
- `interface/api` と `interface/entrypoint/cui` は domain / usecase を直接 import しない
- usecase 接続は `interface/application` から `werewolf_agent.usecase.jobs` の top-level import に閉じる。FakeLLM 設定だけは `domain.llm` の公開面から組み立てる
- domain へ入る usecase code は `usecase/internal` と public port に限定し、`usecase/jobs` は薄い公開 facade にする
- HTTP response schema、Problem Details、error code metadata は `contracts` に置き、FastAPI 例外変換は `interface/shared` に置く
- CLI 表示、画面向けの表示名や整形は interface に閉じる
- public state / public event に role、night action、secret を出さない

詳細は [docs/domain.md](docs/domain.md)。

## 設定

設定 default は `backend/src/werewolf_agent/default_settings/defaults.toml` に置きます。
`commons/configuration` が `defaults.toml`、`.env`、環境変数を読み取り、interface の浅い場所で usecase へ依存として注入します。
`.env` はコミットしません。

主な値:

```env
WEREWOLF_LLM_PROVIDER=fake_llm
WEREWOLF_MODEL=fake-llm-local
WEREWOLF_LLM_TIMEOUT_SECONDS=30
WEREWOLF_LLM_MAX_RETRIES=2
WEREWOLF_LLM_TEMPERATURE=0.7
WEREWOLF_FAKE_LLM_STRATEGY=seeded
WEREWOLF_FAKE_LLM_RANDOMNESS=0.7
WEREWOLF_FAKE_LLM_SPEECH_TEMPLATES=[{persona}] I want to {intent} {target_name}.|[{persona}] {target_name}'s public history looks worth checking.|[{persona}] I will compare today's claims before voting.
WEREWOLF_FAKE_LLM_PERSONA_PROFILES=cautious|assertive|analytical
WEREWOLF_FAKE_LLM_SPEECH_INTENTS=question|compare|pressure
WEREWOLF_FAKE_LLM_REASON_TEMPLATES=fake_llm {persona} {action} from public signals|fake_llm {persona} {action} with {intent} intent
WEREWOLF_LOG_LEVEL=INFO
WEREWOLF_LOG_OUTPUT=file
WEREWOLF_LOG_DIR=.werewolf-agent/logs
WEREWOLF_LOG_FILE_NAME=werewolf-agent.jsonl
WEREWOLF_LOG_RETENTION_DAYS=14
WEREWOLF_LOG_THIRD_PARTY_LEVEL=WARNING
WEREWOLF_CLI_API_URL=http://127.0.0.1:8000/api/v1
WEREWOLF_CLI_HTTP_TIMEOUT_SECONDS=10
WEREWOLF_CLI_MAX_STEPS=64
WEREWOLF_CLI_POLL_INTERVAL_SECONDS=0
WEREWOLF_CLI_EVENT_LIMIT=100
WEREWOLF_CLI_OUTPUT_FORMAT=table
WEREWOLF_GAME_MIN_PLAYERS=5
WEREWOLF_GAME_MAX_PLAYERS=8
WEREWOLF_GAME_DEFAULT_PLAYER_COUNT=6
WEREWOLF_GAME_SUPPORTED_AGENT_TYPE=llm
WEREWOLF_GAME_SUPPORTED_AGENT_NAME=LLM Agent
WEREWOLF_GAME_DEFAULT_RULESET_ID=default
WEREWOLF_GAME_DEFAULT_RULESET_NAME=MVP Default
WEREWOLF_GAME_RULESET_DESCRIPTION_TEMPLATE={min_players}〜{max_players}人向けの最小同期 API ルールセットです。
WEREWOLF_GAME_ROLE_NAMES=villager:村人,werewolf:人狼,seer:占い師,knight:騎士
WEREWOLF_GAME_PHASE_NAMES=night:夜,day_discussion:昼チャット,voting:投票,finished:終了
WEREWOLF_API_TITLE=Werewolf Agent API
WEREWOLF_API_VERSION=0.1.0
WEREWOLF_API_DEBUG=true
WEREWOLF_CORS_ALLOWED_ORIGINS=
WEREWOLF_CORS_ALLOWED_METHODS=GET,POST
WEREWOLF_CORS_ALLOWED_HEADERS=*
WEREWOLF_SQLITE_PATH=.werewolf-agent/db/db.sqlite3
WEREWOLF_DATABASE_URL=
```

DB は設定値で選びます。`WEREWOLF_DATABASE_URL` が空なら SQLite を使い、既定の出力先は `.werewolf-agent/db/db.sqlite3` です。Postgres などを使う場合は `WEREWOLF_DATABASE_URL` を設定します。コード上の `WEREWOLF_API_DEBUG` 既定値は `false` で、`.env.example` と `compose.yaml` はローカル開発用に `true` を明示しています。

運用ログは既定で `.werewolf-agent/logs/werewolf-agent.jsonl` に ECS 風 field の JSON Lines で出力し、UTC の日次 rollover と保持日数で管理します。`WEREWOLF_LOG_OUTPUT` は `file`、`stderr`、`stdout`、`both`、`none` を選べます。`DEBUG` は操作追跡、`INFO` は通常運用、`WARNING` は回復可能な異常、`ERROR` は処理失敗、`CRITICAL` は停止級の異常に使います。public event JSONL は `--log-jsonl` の replay 用ログであり、運用ログとは別です。

## Docker

SQLite:

```bash
docker compose build
docker compose run --rm migrate
docker compose up api
```

Postgres:

```bash
docker compose -f compose.yaml -f compose.postgres.yaml run --rm migrate
docker compose -f compose.yaml -f compose.postgres.yaml up api
```

## 検証

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy backend/src
uv run --extra api alembic upgrade head
uv run --extra api uvicorn werewolf_agent.interface.api.app:create_app --factory
```

## ドキュメント

- [docs/domain.md](docs/domain.md): domain core と境界
- [docs/api.md](docs/api.md): 公開 API 契約
- [docs/development.md](docs/development.md): 再開用メモ

## 次の一手

- 実 LLM provider adapter と structured output validation
- 複数 human player / external agent action API
- 永続 login/session による private observation 認証
- Streamlit / React UI
- evaluation workflow

## License

MIT License
