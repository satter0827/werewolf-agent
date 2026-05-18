# 開発メモ

このドキュメントは、Werewolf Agent の開発を途中から再開しやすくするための入口です。
人間も AI エージェントも、まずここを読めば「今どこで、次に何をすればよいか」が分かる状態を保ちます。

## 現在の目的

- バックエンドのゲーム進行を優先する
- Python 実装は `backend/src/werewolf_agent/` に置く
- まずは CLI から 1 ゲームを完走できる状態を目指す
- LLM 接続より先に、dummy agent と決定的なゲームエンジンを検証可能にする

## よく使うコマンド

```bash
uv sync --group dev
uv run werewolf-agent doctor
uv run --extra api pytest tests/test_api_games.py tests/test_cli.py
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy backend/src
```

必要になったタイミングで optional dependencies を追加します。

```bash
uv sync --group dev --extra api
uv sync --group dev --extra llm
```

Django API の基本コマンド:

```bash
uv run --extra api python backend/manage.py migrate
uv run --extra api python backend/manage.py check
uv run --extra api pytest tests/test_api_health.py tests/test_api_errors.py tests/test_api_games.py
uv run --extra api python backend/manage.py runserver
```

起動後の health endpoint:

```text
http://127.0.0.1:8000/api/health/
http://127.0.0.1:8000/api/rulesets/default/
```

CLI から 1 ゲームを実行する例:

```bash
uv run werewolf-agent play --api-url http://127.0.0.1:8000/api --players 6 --seed 1
uv run werewolf-agent play --api-url http://127.0.0.1:8000/api --players 6 --seed 1 --log-jsonl runs/game-001.jsonl
```

CLI は HTTP API の公開 DTO だけを使い、`domain` / `application` / `agents` を直接 import しません。

Docker Compose v2 を使う場合:

```bash
docker compose build
docker compose run --rm migrate
docker compose up api
docker compose run --rm test
```

Compose の標準構成は Django API を hot reload で起動し、SQLite DB を Docker named volume に保存します。
Windows と macOS では Docker Desktop 上で同じコマンドを使います。

Postgres を使ってクラウドに近い構成を確認する場合:

```bash
docker compose -f compose.yaml -f compose.postgres.yaml run --rm migrate
docker compose -f compose.yaml -f compose.postgres.yaml up api
docker compose -f compose.yaml -f compose.postgres.yaml run --rm test
```

本番用 container は `docker/backend.Dockerfile` の `runtime` target を使い、Gunicorn で起動します。
本番では `WEREWOLF_DJANGO_DEBUG=false`、強い `WEREWOLF_DJANGO_SECRET_KEY`、公開ホストに合わせた `WEREWOLF_DJANGO_ALLOWED_HOSTS`、必要に応じて `WEREWOLF_DATABASE_URL` を設定します。
Migration は container 起動時に自動実行せず、クラウド側の release command または one-off job で `python backend/manage.py migrate` を実行します。

ホスト OS 上の LM Studio などへ Docker container から接続する場合は、base URL に `host.docker.internal` を使います。
例: `http://host.docker.internal:1234/v1`。

Django の実装コードは `backend/src/werewolf_agent/interfaces/api/` 配下に置きます。`backend/manage.py` は Django 標準の操作入口として残します。

新しい Django app を追加する場合:

```bash
cd backend
mkdir src/werewolf_agent/interfaces/api/<app_name>
uv run --extra api python manage.py startapp <app_name> src/werewolf_agent/interfaces/api/<app_name>
```

## VS Code / Cursor

- formatter、linter、import sorter は Ruff に統一する
- `ms-python.flake8` はこの workspace では使わない
- `ms-python.isort` はこの workspace では使わない
- isort の crash 通知が残る場合は、まず VS Code / Cursor の window reload を行う
- Flake8 や isort の通知が reload 後も残る場合は、この workspace で該当拡張を disable する

## どこに何を書くか

- `backend/src/werewolf_agent/config.py`: `.env` と環境変数から読む共通設定
- `backend/src/werewolf_agent/domain/`: ルール、状態、役職、勝敗判定
- `backend/src/werewolf_agent/application/`: ゲーム進行のユースケース
- `backend/src/werewolf_agent/agents/`: dummy、scripted、human、LLM agent
- `backend/src/werewolf_agent/llm/`: provider adapter、prompt、structured output parser
- `backend/src/werewolf_agent/observation/`: JSONL ログ、リプレイ、評価
- `backend/src/werewolf_agent/interfaces/`: CLI、API、Notebook、Streamlit など
- `backend/src/werewolf_agent/interfaces/api/`: Django config、Django app、DRF API
- `tests/`: ルールと境界の再現テスト
- `docs/`: 仕様、判断理由、未決事項

Domain core の公開境界と実装方針は [docs/domain.md](domain.md) を参照してください。

## ログ設定

- アプリログは CLI と Django の入口で初期化し、domain 層には出力先の設定を持ち込まない
- `WEREWOLF_LOG_LEVEL`: `DEBUG`、`INFO`、`WARNING`、`ERROR`、`CRITICAL`
- `WEREWOLF_LOG_FORMAT`: `json` または `console`
- `WEREWOLF_LOG_OUTPUT`: `stderr` または `stdout`
- ゲーム再現・分析向けのログは、アプリログとは別に `JsonlEventWriter` / `EventSink` で JSONL として扱う
- `secret`、`token`、`api_key`、`authorization`、`password` 系のキーはログ出力前にマスクする

## エラーコード方針

- アプリ共通の安全な例外は `werewolf_agent.commons` パッケージの `AppError` とカテゴリ別例外を使う
- コードは `config.invalid_value`、`game.invalid_phase`、`llm.provider_unavailable` のような namespaced slug にする
- API は RFC 9457 Problem Details (`application/problem+json`) を返し、`code` を後方互換のある機械処理キーとして扱う
- Pydantic / DRF の validation error は独自コードへ潰さず、各フィールドの `errors[].code` に既存コードを残す
- CLI は Typer / Click の引数エラーをそのまま使い、`AppError` だけを安全な表示と exit code `1` に変換する

## バイブコーディング向けドキュメント方針

- ドキュメントは、途中参加した人間や AI がすぐ再開できる形にする
- 各 docs は「目的」「現在の状態」「実行コマンド」「完了条件」「未決事項」を優先する
- 長い背景説明より、次の一手が分かる構造を優先する
- 不確かな仕様は断定せず、前提・未決・選択肢として残す
- 実装が動いたら、動かしたコマンドと結果を短く残す

## Handoff メモ形式

作業を中断するときは、以下の形で残します。

```markdown
## Handoff

- 目的:
- 完了:
- 未完了:
- 実行したコマンド:
- 次に見るファイル:
- 判断が必要なこと:
```

## 未決事項

- ゲーム API は、CLI で 1 ゲームを完走するための公開状態取得とステップ進行まで導入済み
- LangChain/実 LLM provider は dummy agent でゲーム進行が固まってから導入する
- `front-web/` は backend の明示的な API/DTO が見えてから着手する
