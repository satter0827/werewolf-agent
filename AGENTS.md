# AGENTS.md

このファイルは、このリポジトリで作業する AI コーディングエージェント向けの作業ガイドです。
リポジトリ全体に適用します。下位に別の `AGENTS.md` がある場合は、そちらを優先してください。

## Project

Werewolf Agent は、LLM agent を人狼ゲームのプレイヤーとして動かす Python backend です。
ゲームルールは deterministic domain core が管理し、外側には公開状態と public timeline だけを出します。

現在の状態:

- CLI / Streamlit は `GameApi` port 経由で Supabase Data API または local demo API に接続する
- Supabase 未ログイン時は local demo API が usecase を直接実行し、既定の FakeListLLM で 1 game を完走できる
- `domain`、`usecase`、CLI、Streamlit、Supabase worker、public timeline、個人履歴、LLM trace は実装済み
- 実 LLM provider QA、複数 manual player、React UI は未実装

## Read First

変更前に、近い実装・テスト・文書を確認してください。

- 入口: `README.md`
- domain 境界: `docs/design/domain.md`
- API 契約: `docs/design/api.md`
- 再開メモ: `docs/notes/development.md`
- Sphinx 入口: `docs/sphinx/index.md`

## Architecture

| Path | 責務 |
| --- | --- |
| `backend/src/werewolf_agent/domain/game/` | ルール、状態、観測、勝敗、game event |
| `backend/src/werewolf_agent/domain/llm/` | provider 非依存の agent 観測 DTO、意思決定 DTO、LangChain provider、prompt loader、provider port |
| `backend/src/werewolf_agent/resources/` | packaged defaults、MLflow-compatible prompt、FakeListLLM response fixture |
| `backend/src/werewolf_agent/usecase/jobs/` | API adapter 向けの薄い usecase facade、DTO、repository port |
| `backend/src/werewolf_agent/usecase/internal/` | usecase workflow、projection、agent adapter、唯一の domain 接点 |
| `backend/src/werewolf_agent/api/` | `GameApi` port、factory、usecase bridge、setup options |
| `backend/src/werewolf_agent/api/local_demo/` | 未ログイン用 process-local game API |
| `backend/src/werewolf_agent/api/supabase/` | Supabase Auth / Data API client、session store |
| `backend/src/werewolf_agent/api/supabase/worker/` | Supabase queue worker、Postgres repository、LLM trace sink |
| `backend/src/werewolf_agent/entrypoint/cui/` | Typer CLI、Supabase login、`GameApi` port 経由の操作 |
| `backend/src/werewolf_agent/entrypoint/streamlit/` | Streamlit 画面、画面状態、表示 model |
| `backend/src/werewolf_agent/entrypoint/requests.py` | CLI / Streamlit 共通 request builder |
| `backend/src/werewolf_agent/contracts/` | Pydantic 外部契約、error code、safe exception、Problem Details |
| `backend/src/werewolf_agent/commons/` | configuration、resources、logging、message catalog、redaction、shared helper |
| `tests/unit/api/` | API adapter unit test |
| `tests/unit/entrypoint/` | CLI / Streamlit unit test |
| `tests/unit/commons/` | configuration、resource、logging unit test |

境界ルール:

- domain は `.env`、Supabase、SQLAlchemy、LLM provider、file I/O、logging 設定に依存させない
- CLI / Streamlit は domain / usecase を直接 import せず、public wire schema と `GameApi` port だけを使う
- `api` は `entrypoint` に依存しない
- `api` から usecase を呼ぶ場所は `api/usecase_bridge.py`、`api/setup_options.py`、`api/local_demo/`、`api/supabase/worker/`、`api/telemetry.py` に限定する
- `api/usecase_bridge.py` は `werewolf_agent.usecase.jobs` の top-level 公開面だけを import する
- `usecase/jobs` は domain を import せず、public DTO と stateless facade に限定する
- usecase から domain を参照する code は `usecase/internal` 配下に限定し、`domain.game.*` と `domain.llm.*` の公開面だけを使う
- `usecase/internal` は API / entrypoint / wire schema に依存させない
- `domain.game` と `domain.llm` は互いに import せず、`usecase.internal` が observation / decision / action を変換してつなぐ
- 業務要件は usecase、コアルールは domain、CLI / 画面向け変換は entrypoint、外部サービス adapter は api に置く
- worker は `private_state` を保存してよいが、公開 DTO や public timeline へ role / night action / secret を出さない
- LLM に渡す情報は、その player が観測できる情報だけにする
- LLM 出力は自由文のまま使わず、Pydantic / JSON Schema 相当で検証する

## Commands

基本:

```bash
uv sync --group dev --extra worker --extra streamlit --extra llm
uv run werewolf-agent doctor
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run --no-sync ruff check --no-cache --select D --ignore D100,D104 backend/src/werewolf_agent
uv run mypy backend/src
```

Supabase worker:

```bash
supabase migration up
uv run --extra worker werewolf-agent-worker run
```

CLI で 1 game 確認:

```bash
uv run werewolf-agent play --role-count werewolf=1 --role-count seer=1 --role-count knight=1 --role-count villager=3 --seed 1
```

Streamlit:

```bash
uv run --extra streamlit streamlit run backend/src/werewolf_agent/entrypoint/streamlit/app.py
```

Docker:

```bash
docker compose build
docker compose --profile worker up worker
docker compose run --rm test
```

Windows / OneDrive / Codex での実行:

- この checkout は OneDrive の reparse point 配下に置かれることがある。Codex の sandbox から PowerShell で repository 内へ新規生成物を書くと、`Access is denied` や Ruff cache warning が起きる場合がある
- AI は検証用の cache と browser QA screenshot を repository 配下へ直接書かず、`%TEMP%\werewolf-agent` 配下を使う
- 依存関係がすでに同期済みなら、AI は `uv run --no-sync ...` を優先する。Ruff は `--no-cache`、mypy は `--no-incremental` または `%TEMP%` の cache を使う
- まとめて検証する場合は `scripts\check-all.cmd` を使う。この script は pytest / mypy cache を `%TEMP%\werewolf-agent` に置く
- worker の手動 QA は `scripts\run-worker.cmd` を使う
- VS Code の `launch.json` / `tasks.json` から起動する場合も、この方針を維持する

## Working Rules

- 後方互換は原則として維持しない。ユーザーが明示しない限り、既存 UI、保存形式、設定名、内部 DTO、session state、local generated data は破壊的に変更してよい
- 互換レイヤー、migration、旧形式 fallback は原則として作らず、現在の設計品質、疎結合、設定値駆動、UX、テスト容易性を優先する
- 小さく、検証しやすい変更にする
- 既存の設計、命名、依存関係に合わせる
- 関係ないリファクタリングや整形だけの変更を混ぜない
- ユーザーや他エージェントの未コミット変更を勝手に戻さない
- 新しい設定値は安全な default、`.env.example`、README / docs、テストを揃える
- DB、provider、worker、ログは設定値で切り替えられるようにする
- ログファイル名に `vscode`、`codex`、`local` など起動手段や作業者由来のメタ名称を入れない。`worker.jsonl`、`streamlit.jsonl`、`cli.jsonl`、`migrate.jsonl` のように実行される機能・プロセス名で命名する
- 不確かな仕様は断定せず、docs に前提・未決・選択肢として残す
- 大きな構成変更は、先に docs へ意図を残す

## Review Criteria

レビューでは、構文より先に次を見てください。

- README / docs / tests / 近い実装と矛盾していないか
- 設定、provider、model、DB、ログ、秘密情報が hard-code されていないか
- 重複した定数や処理を既存設定、共通関数、標準 API に寄せられるか
- CLI / API / UI 境界で内部例外、stack trace、secret を露出していないか
- public state / public timeline に role、night action、API key、token が混ざらないか
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
- public response と public timeline に private state を出さない

## Documentation

- README は利用者向けの入口として保つ
- 完成版の設計書は `docs/design/` に置く
- 修正の積み重ね、判断履歴、handoff は `docs/notes/` に置く
- Sphinx の設定、入口、軽い見た目調整は `docs/sphinx/` に置く
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

外部 API なしで動く LangChain fake / mock provider を先に実装できる場合は、そちらを優先してください。

## Commit Message

日本語を基本にし、Conventional Commits に近い形式にしてください。

例:

- `feat: Supabase worker の queue 処理を追加`
- `fix: public timeline から秘匿情報を除外`
- `docs: 開発メモを最新化`
