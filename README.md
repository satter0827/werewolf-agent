# Werewolf Agent

LLM agent を人狼ゲームのプレイヤーとして動かす Python backend です。
ゲームの真実は deterministic domain core が持ち、外側には公開状態と public event だけを出します。

## 現在地

- 5〜8 人の同期ゲームを実行できる
- 役職は `villager`、`werewolf`、`seer`、`knight`
- フェーズは `night`、`day_discussion`、`voting`、`finished`
- `fake_llm` provider で FastAPI 経由の 1 ゲームを CLI から完走できる
- API は game 作成、状態取得、一覧、1 step 進行、public event、turn history、public SSE を持つ
- CLI は `play`、`watch`、`replay`、`runs`、`turns` を持つ
- 実 LLM provider、手動 action API、private observation API、Streamlit / React UI は未実装

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

## API

| Method | Path | 用途 |
| --- | --- | --- |
| `GET` | `/api/v1/health` | health check |
| `GET` | `/api/v1/rulesets/default` | MVP ruleset metadata |
| `POST` | `/api/v1/games` | game run 作成 |
| `GET` | `/api/v1/games` | game run 一覧 |
| `GET` | `/api/v1/games/{game_id}` | 公開状態取得 |
| `POST` | `/api/v1/games/{game_id}/steps` | 1 step 進行 |
| `GET` | `/api/v1/games/{game_id}/events?after=<seq>` | public event 取得 |
| `GET` | `/api/v1/games/{game_id}/events/stream?after=<seq>` | public event SSE |
| `GET` | `/api/v1/games/{game_id}/turns?after=<seq>` | UI 向け public timeline |

詳細は [docs/api.md](docs/api.md)。

## 設計

| Path | 責務 |
| --- | --- |
| `backend/src/werewolf_agent/domain/game/` | ルール、状態、観測、勝敗、game event |
| `backend/src/werewolf_agent/domain/llm/` | provider 非依存の agent 観測 DTO、意思決定 DTO、FakeLLM decision |
| `backend/src/werewolf_agent/usecase/jobs/` | stateless workflow、業務 validation、repository port、domain 接続 |
| `backend/src/werewolf_agent/interface/api/` | FastAPI、HTTP 入出力、例外変換、SSE |
| `backend/src/werewolf_agent/interface/application/` | usecase adapter、SQLAlchemy repository、transaction、依存注入 |
| `backend/src/werewolf_agent/interface/entrypoint/cui/` | Typer CLI と public HTTP client |
| `backend/src/werewolf_agent/interface/shared/` | settings、logging、wire schema、runtime helper |
| `backend/src/werewolf_agent/interface/entrypoint/streamlit/` | 将来の Streamlit 入口 |
| `backend/src/werewolf_agent/contracts/` | safe exception |
| `backend/src/werewolf_agent/commons/` | error code、message catalog、event sink、redaction、shared helper |

境界:

- `domain` は `.env`、I/O、logging 設定、LLM provider を知らない
- `domain.game` と `domain.llm` は互いに import せず、usecase が observation / decision / action を変換して接続する
- `interface/api` と `interface/entrypoint/cui` は domain / usecase を直接 import しない
- usecase 接続は `interface/application` から `werewolf_agent.usecase.jobs` の top-level import に閉じる。FakeLLM 設定だけは `domain.llm` の公開面から組み立てる
- domain へ入る usecase code は `usecase/jobs` 配下に限定し、触る domain は `domain.game.*` と `domain.llm.*` の公開面だけ
- HTTP response schema、Problem Details、CLI 表示、画面向けの表示名や整形は interface に閉じる
- public state / public event に role、night action、secret を出さない

詳細は [docs/domain.md](docs/domain.md)。

## 設定

設定は `.env` と環境変数から `interface/shared/settings.py` に集約します。
interface の浅い場所で読み取り、usecase へ依存として注入します。
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
WEREWOLF_LOG_FORMAT=json
WEREWOLF_LOG_OUTPUT=stderr
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
- human / LLM action を投入する API
- private observation の認証
- Streamlit / React UI
- evaluation workflow

## License

MIT License
