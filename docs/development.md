# 開発メモ

途中参加した人間や AI が、最短で再開するための作業メモです。

## 現在地

- 優先対象は backend。
- deterministic domain core は実装済み。
- dummy agent は実装済み。
- Django API は game 作成、状態取得、step 進行、public event 取得まで実装済み。
- CLI `play` は公開 HTTP API だけで 1 ゲームを完走できる。
- 実 LLM provider、手動 action API、観戦 UI は未実装。

## まず実行する

```bash
uv sync --group dev
uv run werewolf-agent doctor
uv run pytest
```

API を触る場合:

```bash
uv sync --group dev --extra api
uv run --extra api python backend/manage.py migrate
uv run --extra api python backend/manage.py check
uv run --extra api pytest tests/integration/api
uv run --extra api python backend/manage.py runserver
```

CLI で API 経由のゲームを確認:

```bash
uv run werewolf-agent play --api-url http://127.0.0.1:8000/api --players 6 --seed 1
```

## 品質確認

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy backend/src
uv run --extra api python backend/manage.py check
```

## Optional Dependencies

```bash
uv sync --group dev --extra api
uv sync --group dev --extra llm
```

`api` は Django / DRF / DB adapter 用です。
`llm` は LangChain / OpenAI compatible provider 用です。

## ローカル生成物

Git 管理しないキャッシュ、SQLite、静的ファイル、JSONL ログは `.werewolf-agent/` 配下に集約します。
このディレクトリ配下は `.gitkeep` 以外コミットしません。

## Docker

SQLite:

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

Runtime image:

```bash
docker build --target runtime -f docker/backend.Dockerfile -t werewolf-agent-api:runtime .
```

Production 相当では `WEREWOLF_DJANGO_DEBUG=false`、強い `WEREWOLF_DJANGO_SECRET_KEY`、公開 host に合わせた `WEREWOLF_DJANGO_ALLOWED_HOSTS` を設定します。
起動時 migration はしません。release command または one-off job で `python backend/manage.py migrate` を実行します。

## 配置

| Path | 責務 |
| --- | --- |
| `backend/src/werewolf_agent/config.py` | `.env` / 環境変数 |
| `backend/src/werewolf_agent/domain/models.py` | 外部参照する domain class / enum / type alias / Protocol |
| `backend/src/werewolf_agent/domain/service.py` | 外部参照するステートレス domain 関数 |
| `backend/src/werewolf_agent/domain/rules/` | domain 内部の deterministic rules |
| `backend/src/werewolf_agent/agents/` | dummy / LLM / human agent |
| `backend/src/werewolf_agent/llm/` | provider adapter、prompt、parser |
| `backend/src/werewolf_agent/interfaces/cli.py` | CLI |
| `backend/src/werewolf_agent/interfaces/api/` | Django API、公開 DTO、DB 永続化 |
| `backend/src/werewolf_agent/contracts/` | error code、safe exception、Problem Details schema |
| `backend/src/werewolf_agent/commons/` | logging、events、security、shared constants など内部横断 helper |
| `tests/unit/` | プロセス内で完結する unit test |
| `tests/integration/` | Django / API / DB など複数層を接続する integration test |
| `docs/` | 設計、契約、未決事項 |

## テスト構成

`tests/` は実装境界ごとに配置します。

```text
tests/
  unit/
    agents/
    commons/
    config/
    contracts/
    domain/
    interfaces/
      cli/
  integration/
    api/
```

- `unit/`: プロセス内で完結し、DB、Django test client、外部 HTTP、実 LLM provider を使わないテスト。
- `integration/`: Django / DRF、DB setup、HTTP endpoint、CLI から API への接続など、複数層の接続を検証するテスト。
- CLI テストは fake API client で公開 API 境界を検証する限り `tests/unit/interfaces/cli/` に置く。実 API サーバや Django client を使う場合は `tests/integration/cli/` を追加する。
- LLM の mock provider テストは `tests/unit/llm/`、実 provider や optional dependency を含む接続確認は `tests/integration/llm/` に置く。

## 設計メモ

- CLI は domain / agents を直接 import しない。HTTP API の DTO だけを使う。
- domain は Django、LLM provider、I/O、logging 設定に依存しない。
- domain 外から domain を参照する場合は `domain.models` と `domain.service` だけを使う。
- `domain.rules` は `models` / `service` から使う内部実装として扱う。
- API は `private_state` を保存してよいが、公開 DTO に出さない。
- public event には role、night action、secret、token、API key を含めない。
- `AppError` は CLI では短いメッセージ、API では Problem Details に変換する。
- Pydantic / DRF validation error の field code は潰さない。

## VS Code / Cursor

- Ruff を formatter / linter / import sorter として使う。
- Flake8 / isort 拡張はこの workspace では使わない。
- `.vscode/launch.json` は共有してよいが、ローカル固定パスや secret を入れない。

## 未決事項

- LLM provider adapter と prompt 管理
- 人間プレイヤー / 外部 LLM からの action 投入 API
- private observation の認証と権限
- SSE / WebSocket による観戦 event 配信
- Streamlit または React UI
- replay / evaluation workflow

## Handoff

中断時は次だけ残します。

```markdown
## Handoff

- 目的:
- 完了:
- 未完了:
- 実行したコマンド:
- 次に見るファイル:
- 判断が必要なこと:
```
