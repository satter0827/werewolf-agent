# AGENTS.md

このファイルは、このリポジトリで作業する AI コーディングエージェント向けの作業ガイドです。
リポジトリ全体に適用します。下位に別の `AGENTS.md` がある場合は、そちらを優先してください。

## Project

Werewolf Agent は、LLM agent を人狼ゲームのプレイヤーとして動かす Python backend です。
ゲームルールは deterministic domain core が管理し、外側には公開状態と public event だけを出します。

現在の状態:

- `fake_llm` provider だけで FastAPI 経由の 1 game を CLI から完走できる
- `domain`、`usecase`、FastAPI、CLI、public event stream、turn read model は実装済み
- 実 LLM provider、手動 action API、private observation API、Streamlit / React UI は未実装

## Read First

変更前に、近い実装・テスト・文書を確認してください。

- 入口: `README.md`
- domain 境界: `docs/domain.md`
- API 契約: `docs/api.md`
- 再開メモ: `docs/development.md`

## Architecture

| Path | 責務 |
| --- | --- |
| `backend/src/werewolf_agent/domain/game/` | ルール、状態、観測、勝敗、game event |
| `backend/src/werewolf_agent/domain/llm/` | provider 非依存の agent 観測 DTO、意思決定 DTO、FakeLLM decision、provider port |
| `backend/src/werewolf_agent/usecase/jobs/` | stateless workflow、業務 validation、repository port、domain 接続 |
| `backend/src/werewolf_agent/interface/entrypoint/api/` | FastAPI、HTTP 入出力、例外変換、SSE |
| `backend/src/werewolf_agent/interface/application/` | usecase adapter、DB repository、transaction、依存注入 |
| `backend/src/werewolf_agent/interface/entrypoint/cui/` | 公開 HTTP API だけを呼ぶ CLI |
| `backend/src/werewolf_agent/interface/shared/` | settings、logging、wire schema、runtime helper |
| `backend/src/werewolf_agent/interface/entrypoint/streamlit/` | 将来の Streamlit 入口 |
| `backend/src/werewolf_agent/contracts/` | safe exception |
| `backend/src/werewolf_agent/commons/` | error code、message catalog、event sink、redaction、shared helper |
| `tests/unit/` | unit test |
| `tests/integration/api/` | FastAPI / DB / API integration test |

境界ルール:

- domain は `.env`、FastAPI、SQLAlchemy、LLM provider、file I/O、logging 設定に依存させない
- CLI は domain / usecase を直接 import せず、public wire schema と HTTP client だけを使う
- `interface/entrypoint/api` と `interface/entrypoint/cui` は domain / usecase を直接 import しない
- interface 層から usecase を呼ぶ場所は `interface/application/` に限定する
- `interface/application` は `werewolf_agent.usecase.jobs` の top-level 公開面だけを import する
- usecase から domain を参照する code は `usecase/jobs` 配下に限定し、`domain.game.*` と `domain.llm.*` の公開面だけを使う
- `domain.game` と `domain.llm` は互いに import せず、usecase が observation / decision / action を変換してつなぐ
- 業務要件は usecase、コアルールは domain、HTTP / CLI / 画面向け変換は interface に置く
- API は `private_state` を保存してよいが、公開 DTO や public event へ role / night action / secret を出さない
- LLM に渡す情報は、その player が観測できる情報だけにする
- LLM 出力は自由文のまま使わず、Pydantic / JSON Schema 相当で検証する

## Commands

基本:

```bash
uv sync --group dev --extra api
uv run werewolf-agent doctor
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy backend/src
```

API:

```bash
uv run --extra api alembic upgrade head
uv run --extra api pytest tests/integration/api
uv run --extra api uvicorn werewolf_agent.interface.entrypoint.api.app:create_app --factory
```

CLI で 1 game 確認:

```bash
uv run werewolf-agent play --api-url http://127.0.0.1:8000/api/v1 --players 6 --seed 1
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
- DB、provider、API、ログは設定値で切り替えられるようにする
- 不確かな仕様は断定せず、docs に前提・未決・選択肢として残す
- 大きな構成変更は、先に docs へ意図を残す

## Review Criteria

レビューでは、構文より先に次を見てください。

- README / docs / tests / 近い実装と矛盾していないか
- 設定、provider、model、DB、ログ、秘密情報が hard-code されていないか
- 重複した定数や処理を既存設定、共通関数、標準 API に寄せられるか
- CLI / API / UI 境界で内部例外、stack trace、secret を露出していないか
- public state / public event に role、night action、API key、token が混ざらないか
- 変更範囲に見合う test、lint、format check、type check を実行したか
- 不要となったファイル、モジュールを残していないか

## Testing

- ルール、勝敗、投票、夜行動は unit test を優先する
- LLM provider 直接呼び出しは通常 unit test から分離する
- LLM 出力は mock / fixture で再現可能にする
- ランダム性を使うテストは seed を固定する
- バグ修正では、可能な限り再現テストを追加する

## Security

- `.env`、API key、token、秘密鍵をコミットしない
- `.env.example` はダミー値だけにする
- ログ出力前に `secret`、`token`、`api_key`、`authorization`、`password` 系を mask する
- 外部入力をそのまま prompt、file path、shell command に渡さない
- public response と public event に private state を出さない

## Documentation

- README は利用者向けの入口として保つ
- 詳細設計と判断理由は `docs/` に置く
- 文書は日本語を基本にし、コード識別子と外部 API 名は英語のまま扱う
- 「目的」「現在地」「実行コマンド」「未実装」「次の一手」を優先する
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

外部 API なしで動く FakeLLM / mock provider を先に実装できる場合は、そちらを優先してください。

## Commit Message

日本語を基本にし、Conventional Commits に近い形式にしてください。

例:

- `feat: FastAPI 経由のゲーム進行を追加`
- `fix: public event から秘匿情報を除外`
- `docs: 開発メモを最新化`
