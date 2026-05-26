# Werewolf Agent

LLM エージェントを人狼ゲームのプレイヤーとして動かすポートフォリオプロジェクトです。
ゲームルールは決定的な Python engine が管理し、エージェントは観測できる情報だけを受け取って発話・投票・夜行動を返します。

> Status: dummy agent だけで、Django API 経由の 1 ゲームを CLI から完走できます。次は実 LLM provider、private action API、観戦 UI です。

## 今できること

- 5〜8 人ゲーム
- 役職: 村人、人狼、占い師、騎士
- フェーズ: 夜、昼チャット、投票、終了
- seed 付きの再現可能な進行
- Django API によるゲーム作成、ステップ進行、公開イベント取得
- CLI `werewolf-agent play` による API 経由の 1 ゲーム実行
- 公開状態と秘匿状態の分離

## 設計の要点

- `domain`: ルール、状態、投票、夜行動、勝敗判定。`.env`、Django、ログ出力に依存しない。
- `agents`: `Observation` を受け取り、構造化 action を返す。現在は `FakeLlmAgent` のみ。
- `interfaces/api`: Django / DRF の公開 API。公開 DTO を定義し、`GameSnapshot` を保存・変換する。
- `interfaces/cli.py`: 公開 HTTP API だけを呼ぶ。domain / agents を直接 import しない。
- `contracts`: 安定した error code、safe exception、Problem Details schema。外部境界で共有する契約。
- `commons`: アプリログ、JSONL event、redaction など内部で横断的に使う helper。

## セットアップ

```bash
uv sync --group dev
uv run werewolf-agent doctor
```

API を使う場合:

```bash
uv sync --group dev --extra api
uv run --extra api python backend/manage.py migrate
uv run --extra api python backend/manage.py runserver
```

別ターミナルで 1 ゲーム実行:

```bash
uv run werewolf-agent play --api-url http://127.0.0.1:8000/api --players 6 --seed 1
```

公開イベントを JSONL に残す場合:

```bash
uv run werewolf-agent play --api-url http://127.0.0.1:8000/api --players 6 --seed 1 --log-jsonl runs/game-001.jsonl
```

## API

主要 endpoint:

- `GET /api/health/`
- `GET /api/rulesets/default/`
- `POST /api/games/`
- `GET /api/games/{game_id}/`
- `POST /api/games/{game_id}/steps/`
- `POST /api/games/{game_id}/advance/`
- `GET /api/games/{game_id}/events/?after=<sequence>`

詳細は [docs/api.md](docs/api.md) を参照してください。

## 設定

設定は `.env` と環境変数から [backend/src/werewolf_agent/config.py](backend/src/werewolf_agent/config.py) に集約します。

よく使う値:

```env
WEREWOLF_LLM_PROVIDER=dummy
WEREWOLF_MODEL=dummy-local
WEREWOLF_LOG_LEVEL=INFO
WEREWOLF_LOG_FORMAT=json
WEREWOLF_LOG_OUTPUT=stderr
WEREWOLF_DJANGO_DEBUG=true
WEREWOLF_DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,testserver
WEREWOLF_DATABASE_URL=
```

`.env` はコミットしません。`WEREWOLF_DJANGO_DEBUG=false` では、既定の開発用 secret key のまま起動できません。

## Docker

SQLite のローカル API:

```bash
docker compose build
docker compose run --rm migrate
docker compose up api
```

Postgres 付き:

```bash
docker compose -f compose.yaml -f compose.postgres.yaml run --rm migrate
docker compose -f compose.yaml -f compose.postgres.yaml up api
```

Runtime image:

```bash
docker build --target runtime -f docker/backend.Dockerfile -t werewolf-agent-api:runtime .
```

本番起動時は migration を自動実行しません。release command または one-off job で `python backend/manage.py migrate` を実行してください。

## 検証

```bash
uv run werewolf-agent doctor
uv run pytest
uv run --extra api python backend/manage.py check
uv run --extra api pytest tests/test_api_health.py tests/test_api_errors.py tests/test_api_games.py
uv run ruff check .
uv run ruff format --check .
uv run mypy backend/src
```

## ドキュメント

- [docs/domain.md](docs/domain.md): deterministic core の設計境界
- [docs/api.md](docs/api.md): 公開 API 契約
- [docs/development.md](docs/development.md): 作業再開用の開発メモ

## 次の一手

- 実 LLM provider adapter
- 人間 / LLM が action を投入する API
- private observation / private event の認証設計
- Streamlit または React の観戦 UI
- replay / evaluation 用のログ活用

## ライセンス

MIT License
