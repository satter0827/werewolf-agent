# 開発メモ

このドキュメントは、Werewolf Agent の開発を途中から再開しやすくするための入口です。
人間も AI エージェントも、まずここを読めば「今どこで、次に何をすればよいか」が分かる状態を保ちます。

## 現在の目的

- Backend MVP を優先する
- Python 実装は `backend/src/werewolf_agent/` に置く
- まずは CLI から 1 ゲームを完走できる状態を目指す
- LLM 接続より先に、dummy agent と決定的なゲームエンジンを検証可能にする

## よく使うコマンド

```bash
uv sync --group dev
uv run werewolf-agent doctor
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
uv run --extra api pytest tests/test_api_health.py
uv run --extra api python backend/manage.py runserver
```

起動後の health endpoint:

```text
http://127.0.0.1:8000/api/health/
```

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

## ログ設定

- アプリログは CLI と Django の入口で初期化し、domain 層には出力先の設定を持ち込まない
- `WEREWOLF_LOG_LEVEL`: `DEBUG`、`INFO`、`WARNING`、`ERROR`、`CRITICAL`
- `WEREWOLF_LOG_FORMAT`: `json` または `console`
- `WEREWOLF_LOG_OUTPUT`: `stderr` または `stdout`
- ゲーム再現・分析向けのログは、アプリログとは別に `JsonlEventWriter` / `EventSink` で JSONL として扱う
- `secret`、`token`、`api_key`、`authorization`、`password` 系のキーはログ出力前にマスクする

## エラーコード方針

- アプリ共通の安全な例外は `werewolf_agent.errors` パッケージの `AppError` とカテゴリ別例外を使う
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

- Django/API 層は最小 health endpoint まで導入済み。ゲーム API は CLI MVP の進行に合わせて拡張する
- LangChain/実 LLM provider は dummy agent でゲーム進行が固まってから導入する
- `front-web/` は backend の明示的な API/DTO が見えてから着手する
