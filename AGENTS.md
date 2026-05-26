# AGENTS.md

このファイルは、このリポジトリで作業する AI コーディングエージェント向けの作業ガイドです。
リポジトリ全体に適用します。より深い階層に別の `AGENTS.md` がある場合は、そちらを優先してください。

## Project

Werewolf Agent は、LLM エージェントをプレイヤーとして参加させる人狼ゲームです。
ゲームルールは deterministic engine が管理し、エージェントは観測できる情報だけを受け取って構造化 action を返します。

現在の状態:

- dummy agent だけで Django API 経由の 1 ゲームを CLI から完走できる
- domain core、usecase、API、CLI、public event stream は実装済み
- 実 LLM provider、手動 action API、private observation 認証、観戦 UI は未実装

## Read First

作業前に、変更範囲に近い実装・テスト・文書を確認してください。

- 入口: `README.md`
- domain 境界: `docs/domain.md`
- API 契約: `docs/api.md`
- 開発再開メモ: `docs/development.md`

## Architecture

主要な責務:

- `backend/src/werewolf_agent/domain/`: ルール、状態、投票、夜行動、勝敗判定
- `backend/src/werewolf_agent/usecase/`: interface と domain をつなぐ usecase、公開投影、port
- `backend/src/werewolf_agent/agents/`: dummy agent。実 LLM / human agent は未実装
- `backend/src/werewolf_agent/llm/`: 未実装。将来の provider adapter、prompt、structured output parser 置き場
- `backend/src/werewolf_agent/interfaces/cli.py`: CLI。公開 HTTP API だけを呼ぶ
- `backend/src/werewolf_agent/interfaces/api/`: Django API、公開 DTO、DB adapter、transaction、例外変換
- `backend/src/werewolf_agent/contracts/`: error code、safe exception、Problem Details schema
- `backend/src/werewolf_agent/commons/`: logs、JSONL event、redaction
- `tests/unit/`: domain と外部境界の unit test
- `tests/integration/api/`: Django / API / DB 境界の integration test
- `docs/`: 仕様、判断理由、未決事項

境界ルール:

- domain は `.env`、Django、LLM provider、file I/O、logging 設定に依存させない
- CLI は domain / agents を直接 import せず、API DTO と HTTP client だけを使う
- interface 層は domain / agents を直接 import せず、usecase の stateless function を呼ぶ
- usecase から domain を参照する場合は `domain.models` と `domain.service` だけを使う
- API は `private_state` を保存してよいが、公開 DTO や public event へ role / night action / secret を出さない
- LLM に渡す情報は、その player が観測できる情報だけにする
- LLM 出力は自由文のまま使わず、Pydantic / JSON Schema 相当で検証する

## Commands

基本:

```bash
uv sync --group dev
uv run werewolf-agent doctor
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy backend/src
```

API:

```bash
uv sync --group dev --extra api
uv run --extra api python backend/manage.py migrate
uv run --extra api python backend/manage.py check
uv run --extra api pytest tests/integration/api
uv run --extra api python backend/manage.py runserver
```

CLI で 1 ゲーム確認:

```bash
uv run werewolf-agent play --api-url http://127.0.0.1:8000/api --players 6 --seed 1
```

Docker:

```bash
docker compose build
docker compose run --rm migrate
docker compose up api
docker compose run --rm test
```

## Working Rules

- 小さく、検証しやすい変更にする
- 既存の設計、命名、依存関係に合わせる
- 関係ないリファクタリングや整形だけの変更を混ぜない
- ユーザーや他エージェントの未コミット変更を勝手に戻さない
- 新しい設定値は安全な default、`.env.example`、README / docs、テストを揃える
- 不確かな仕様は断定せず、docs に前提・未決・選択肢として残す
- 大きな構成変更は、先に docs へ意図を残す

## Review Criteria

レビューでは、構文より先に次を見てください。

- 変更が README / docs / tests / 近い実装と矛盾していないか
- 設定、provider、model、DB、Django、ログ、秘密情報が hard-code されていないか
- 重複した定数や処理を既存設定、共通関数、標準 API に寄せられるか
- CLI / API / UI 境界で内部例外、stack trace、secret を露出していないか
- public state / public event に role、night action、API key、token が混ざらないか
- 変更範囲に見合う test、lint、format check、type check を実行したか
- コミットメッセージ案は日本語を基本にし、`feat: ...`、`fix: ...`、`docs: ...` など Conventional Commits に近いデファクトな形式にする
- 不要となったファイル、モジュールを残していないか

## Testing

- ルール、勝敗判定、投票、夜行動は unit test を優先する
- LLM provider 直接呼び出しは通常の unit test から分離する
- LLM 出力は mock / fixture で再現可能にする
- ランダム性を使うテストは seed を固定する
- バグ修正では、可能な限り再現テストを追加する

## Security

- `.env`、API key、token、秘密鍵をコミットしない
- `.env.example` はダミー値だけにする
- ログ出力前に `secret`、`token`、`api_key`、`authorization`、`password` 系を mask する
- 外部入力をそのまま prompt、file path、shell command に渡さない
- `WEREWOLF_DJANGO_DEBUG=false` では強い `WEREWOLF_DJANGO_SECRET_KEY` を必須にする

## Documentation

- README は利用者向けの入口として保つ
- 詳細設計と判断理由は `docs/` に置く
- 文書は日本語を基本にし、コード識別子と外部 API 名は英語のまま扱う
- 「目的」「現在の状態」「実行コマンド」「未決事項」「次の一手」を優先する
- 長い背景説明より、途中参加者がすぐ再開できる構造を優先する

## Style

- コード識別子、ファイル名、API field は英語
- Python docstring は Google style
- コメントは、意図や制約がコードから読み取りにくい場合だけ書く
- 例外メッセージとログは、原因と次の調査手順が分かる内容にする
- formatter / linter / import sorter は Ruff

## When Blocked

不足している依存関係、API key、外部サービス、未確定仕様がある場合は、次を残してください。

- 何が不足しているか
- どこまで完了したか
- 実行したコマンド
- 次に人間が判断すべき選択肢

可能なら、外部 API なしで動く dummy agent / mock provider を先に実装してください。

## Commit Message

日本語を基本にし、Conventional Commits に近い形式にしてください。

例:

- `feat: API 経由のゲーム進行を追加`
- `fix: public event から秘匿情報を除外`
- `docs: 開発メモを最新化`
