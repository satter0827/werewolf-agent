# Werewolf Agent

LLM / dummy agent を人狼ゲームのプレイヤーとして動かす Python backend です。
ゲームの真実は deterministic domain core が持ち、外側には公開状態と public event だけを出します。

## 現在地

- 5〜8 人の同期ゲームを実行できる
- 役職は `villager`、`werewolf`、`seer`、`knight`
- フェーズは `night`、`day_discussion`、`voting`、`finished`
- dummy agent だけで Django API 経由の 1 ゲームを CLI から完走できる
- API は game 作成、状態取得、1 step 進行、public event 取得を持つ
- 実 LLM provider、手動 action API、private observation API、観戦 UI は未実装

## 動かす

```bash
uv sync --group dev --extra api
uv run werewolf-agent doctor
uv run --extra api python backend/manage.py migrate
uv run --extra api python backend/manage.py runserver
```

別ターミナル:

```bash
uv run werewolf-agent play --api-url http://127.0.0.1:8000/api --players 6 --seed 1
```

public event を JSONL に残す:

```bash
uv run werewolf-agent play --api-url http://127.0.0.1:8000/api --players 6 --seed 1 --log-jsonl .werewolf-agent/logs/game-001.jsonl
```

## API

| Method | Path | 用途 |
| --- | --- | --- |
| `GET` | `/api/health/` | health check |
| `GET` | `/api/rulesets/default/` | MVP ruleset metadata |
| `POST` | `/api/games/` | game run 作成 |
| `GET` | `/api/games/{game_id}/` | 公開状態取得 |
| `POST` | `/api/games/{game_id}/steps/` | 1 step 進行 |
| `POST` | `/api/games/{game_id}/advance/` | `steps` の互換 alias |
| `GET` | `/api/games/{game_id}/events/?after=<seq>` | public event 取得 |

詳細は [docs/api.md](docs/api.md)。

## 設計

| Path | 責務 |
| --- | --- |
| `backend/src/werewolf_agent/domain/` | ルール、状態、観測、勝敗、domain event |
| `backend/src/werewolf_agent/usecase/` | workflow、projection、port、agent factory |
| `backend/src/werewolf_agent/interfaces/api/` | Django API、HTTP 入出力、Django config、例外変換 |
| `backend/src/werewolf_agent/interfaces/application/` | usecase adapter、DB repository、transaction、依存注入 |
| `backend/src/werewolf_agent/interfaces/cli/` | 公開 HTTP API だけを呼ぶ CLI |
| `backend/src/werewolf_agent/interfaces/shared/` | interface 起動時の runtime helper |
| `backend/src/werewolf_agent/contracts/` | HTTP API schema、error code、Problem Details |
| `backend/src/werewolf_agent/commons/` | logging、event sink、redaction、shared helper |

境界:

- `domain` は Django、`.env`、I/O、logging 設定、LLM provider を知らない
- `interfaces/api` と `interfaces/cli` は domain / usecase を直接 import しない
- usecase 接続は `interfaces/application` に閉じる
- `usecase` が触る domain は `domain.models` と `domain.service` だけ
- public state / public event に role、night action、secret を出さない

詳細は [docs/domain.md](docs/domain.md)。

## 設定

設定は `.env` と環境変数から [backend/src/werewolf_agent/configuration/](backend/src/werewolf_agent/configuration/) に集約します。
interface の浅い場所で読み取り、usecase へ依存として注入します。
既存の `werewolf_agent.config` は互換 import として残しています。
`.env` はコミットしません。

主な値:

```env
WEREWOLF_LLM_PROVIDER=dummy
WEREWOLF_MODEL=dummy-local
WEREWOLF_LOG_LEVEL=INFO
WEREWOLF_LOG_FORMAT=json
WEREWOLF_LOG_OUTPUT=stderr
WEREWOLF_GAME_MIN_PLAYERS=5
WEREWOLF_GAME_MAX_PLAYERS=8
WEREWOLF_GAME_DEFAULT_PLAYER_COUNT=6
WEREWOLF_GAME_SUPPORTED_AGENT_TYPE=dummy
WEREWOLF_GAME_SUPPORTED_AGENT_NAME=Dummy Agent
WEREWOLF_GAME_DEFAULT_RULESET_ID=default
WEREWOLF_GAME_DEFAULT_RULESET_NAME=MVP Default
WEREWOLF_DJANGO_SECRET_KEY=django-insecure-local-dev-only
WEREWOLF_DJANGO_DEBUG=true
WEREWOLF_DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,testserver
WEREWOLF_DJANGO_CSRF_TRUSTED_ORIGINS=
WEREWOLF_DJANGO_SQLITE_PATH=.werewolf-agent/db/db.sqlite3
WEREWOLF_DATABASE_URL=
```

`WEREWOLF_DJANGO_DEBUG=false` では、50 文字以上の独自 `WEREWOLF_DJANGO_SECRET_KEY` が必須です。

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
uv run --extra api python backend/manage.py check
uv run --extra api pytest tests/integration/api
```

## ドキュメント

- [docs/domain.md](docs/domain.md): domain core と境界
- [docs/api.md](docs/api.md): 公開 API 契約
- [docs/development.md](docs/development.md): 再開用メモ

## 次の一手

- 実 LLM provider adapter と structured output validation
- human / LLM action を投入する API
- private observation の認証
- SSE / WebSocket または UI での観戦
- replay / evaluation 用 event workflow

## License

MIT License
