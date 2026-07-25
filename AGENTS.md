# AGENTS.md

このファイルは、このリポジトリで作業する AI コーディングエージェント向けの作業ガイドです。
リポジトリ全体に適用します。下位に別の `AGENTS.md` がある場合は、そちらを優先してください。

## Project

Werewolf Agent は、LLM agent を人狼ゲームのプレイヤーとして動かす Python backend です。
ゲームルールは deterministic domain core が管理し、外側には公開状態と public timeline だけを出します。

現在の状態:

- React / CLI / Streamlit は HTTP API 経由でゲームを操作する
- React から Supabase へ直接接続する用途は Auth だけで、ゲームテーブルは Data API から参照できない
- 既定の FakeListLLM は外部 LLM API を使わず、ログイン済み利用者のgameだけがworker内の有料providerを使う
- `domain`、`GameApplication`、FastAPI、React、Streamlit、CLI、Supabase worker、完全リプレイ、private LLM trace は実装済み
- 実 LLM providerの長時間QAと複数 manual playerは未実装

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
| `src/werewolf_agent/domain/` | 集約、状態、イベント、ルールポリシー |
| `src/werewolf_agent/agents/` | provider 非依存の観測、意思決定、player port |
| `src/werewolf_agent/agents/langchain/` | LangChain provider、graph、prompt処理、FakeListLLM |
| `src/werewolf_agent/resources/` | packaged defaults、MLflow-compatible prompt、FakeListLLM response fixture |
| `src/werewolf_agent/usecase/` | stateless handler、DTO、repository port、projection |
| `src/werewolf_agent/adapters/` | `GameClient` port、HTTP client、factory、usecase bridge、setup options |
| `src/werewolf_agent/adapters/agents/` | usecase と agents を接続する game driver |
| `src/werewolf_agent/adapters/supabase/` | Supabase Auth、repository、operation queue、trace sink |
| `src/werewolf_agent/api/` | FastAPI、認証・認可境界、HTTP composition root |
| `src/werewolf_agent/interfaces/worker/` | operation取得、自動進行、LLM実行 |
| `src/werewolf_agent/interfaces/cli/` | Typer CLI、Supabase login、HTTP `GameClient` 経由の操作 |
| `src/werewolf_agent/interfaces/streamlit/` | Streamlit 画面、画面状態、表示 model |
| `frontend/` | React本番UI、generated OpenAPI client、Browser E2E |
| `src/werewolf_agent/contracts/` | Pydantic 外部契約、error code、safe exception、Problem Details |
| `src/werewolf_agent/configuration/` | settings、resource、definition、message catalog |
| `src/werewolf_agent/observability/` | loggingと実行 context |
| `src/werewolf_agent/security/` | redaction |
| `tests/unit/adapters/` | 外部サービスadapter unit test |
| `tests/unit/interfaces/` | CLI / Streamlit unit test |
| `tests/unit/configuration/` | 設定とresource unit test |
| `tests/unit/observability/` | loggingと実行contextのunit test |
| `tests/unit/security/` | redaction unit test |

境界ルール:

- domain は `.env`、Supabase、SQLAlchemy、LLM provider、file I/O、logging 設定に依存させない
- React / CLI / Streamlit は HTTP API だけでゲームを操作し、合法手、勝敗、フェーズを再計算しない
- CLI / Streamlit は domain / usecase / Supabase repository を直接 import せず、public wire schema と `GameClient` port だけを使う
- React のゲーム通信はgenerated client、Supabase接続はAuth clientだけを使う
- `adapters` は `interfaces` に依存しない
- Python利用者向けusecase公開面はstatelessな`GameApplication`と`Actor`だけに限定する
- usecase は agents / adapters / interfaces に依存しない
- agents は domain / usecase に依存しない
- `adapters/agents/game_driver.py` だけが usecase と agents の observation / decision / action を変換してつなぐ
- domain は他層へ依存せず、外部層は `werewolf_agent.domain` の公開面を使う
- IDを含む利用者要求は usecase、コアルールは domain、CLI / 画面向け変換は interfaces、外部サービス接続は adapters に置く
- usecase はログやテレメトリーを出力せず、interfaces と adapters が外部境界で記録する
- `interfaces/worker` は `private_state` を保存してよいが、公開 DTO や public timeline へ role / night action / secret を出さない
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
uv run --no-sync ruff check --no-cache --select D --ignore D100,D104 src/werewolf_agent
uv run mypy src
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
uv run --extra streamlit streamlit run src/werewolf_agent/interfaces/streamlit/app.py
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
