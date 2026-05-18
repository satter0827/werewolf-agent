# Werewolf Agent

LLM エージェントをプレイヤーとして参加させる人狼ゲームです。
ゲーム進行、役職処理、勝敗判定は決定的なゲームエンジンで管理し、LLM は各プレイヤーの発話、推理、投票、能力使用の意思決定を担当します。

> Status: Backend MVP の開発環境を整備中。まずは CLI から 1 ゲームを完走できる状態を目指します。

## 目的

- LLM 同士がチャット形式の自然言語対話で人狼ゲームを進行できる環境を作る
- ゲームルールと LLM の推論・発話ロジックを分離し、検証しやすい構成にする
- 会話ログ、投票理由、役職行動、勝敗を保存し、後から分析できるようにする
- CLI、Notebook、Web UI など複数のインターフェースから同じゲームエンジンを利用できるようにする

## MVP スコープ

最初の実装では、以下の最小構成を目標にします。

- プレイヤー数: 5〜8 人
- 役職: 村人、人狼、占い師、騎士
- フェーズ: 夜、昼チャット、投票、追放、勝敗判定
- プレイヤー: LLM エージェント、またはルールベースのダミーエージェント
- 実行方法: CLI から 1 ゲームを実行
- 出力: 標準出力と JSONL ログ

## 設計方針

### Deterministic Core

ゲーム状態、役職処理、投票集計、勝敗判定は LLM に委ねず、純粋な Python ロジックとして実装します。これにより、同じ入力に対して再現可能な結果を得られます。

### Agent Layer

LLM エージェントは、ゲーム状態のうち本人に見えてよい情報だけを受け取り、発話、投票、襲撃、占い、護衛などの行動を返します。

LLM の出力は自由文のまま扱わず、JSON Schema や Pydantic モデルで検証できる構造化データに変換します。

### Provider Adapter

OpenAI 互換 API、ローカル LLM、モック LLM を差し替えられるように、モデル呼び出しはアダプター層に閉じ込めます。

### Observability

ログは、運用向けの構造化アプリログと、ゲーム再現・分析向けの JSONL イベントログを分けます。
アプリログは Python 標準 `logging` を使い、CLI と Django の入口で設定します。ゲームエンジンのコアにはログ出力先を持ち込まず、必要な境界で logger や event sink を注入します。

ゲームの再現、デバッグ、評価のために、以下を JSONL イベントログとして保存します。

- ゲーム設定
- 初期役職
- 各フェーズの状態遷移
- 各エージェントへの観測情報
- LLM への入力と構造化された出力
- 投票結果
- 勝敗結果

API キーや機密情報はログに含めません。

### Error Handling

Backend 共通のアプリ起因エラーは `werewolf_agent.errors` パッケージに集約します。エラーコードは `game.invalid_action` のような namespaced slug を使い、独自の数値コードは増やしません。

HTTP API は RFC 9457 Problem Details (`application/problem+json`) を返します。`type`、`title`、`status`、`detail`、`instance` を基本形とし、安定した `code` と、必要に応じて `trace_id`、`errors` を含めます。

入力検証は Pydantic / Django REST Framework の既存エラーコードを尊重します。API 全体の validation error は `request.validation_failed` とし、各フィールドの `errors[]` には Pydantic / DRF の `missing`、`int_parsing`、`required` などのコードを保持します。

CLI は Typer / Click の引数エラーを標準挙動に任せ、アプリ起因の `AppError` だけを安全な短いメッセージと exit code `1` に変換します。

## 技術スタック

- Language: Python 3.11+
- Package Manager: uv
- Validation: Pydantic
- Testing: pytest
- Lint / Format: Ruff
- Type Check: mypy または pyright
- CLI: Typer
- Config: `.env` + 環境変数
- Logs: structured application logs + JSONL game events

## ディレクトリ構成

```text
.
├── backend/
│   └── src/
│       └── werewolf_agent/
│           ├── domain/          # ゲームルール、状態、役職、勝敗判定
│           ├── application/     # ユースケース、ゲーム進行サービス
│           ├── agents/          # LLM / ダミー / 人間プレイヤーの実装
│           ├── llm/             # LLM プロバイダー、プロンプト、構造化出力
│           ├── interfaces/      # CLI、API、Web、Notebook など
│           │   └── api/         # Django config and API apps
│           └── observation/     # ログ、リプレイ、評価
├── front-web/
├── tests/
├── docs/
├── .env.example
├── pyproject.toml
└── README.md
```

## セットアップ

開発環境はリポジトリ直下から整えます。

```bash
uv sync --group dev
cp .env.example .env
uv run werewolf-agent doctor
```

初期状態では dummy provider を使います。実 LLM provider を使う場合だけ `.env` に API キーを設定します。

```env
WEREWOLF_LLM_PROVIDER=dummy
WEREWOLF_MODEL=dummy-local
WEREWOLF_LOG_LEVEL=INFO
WEREWOLF_LOG_FORMAT=json
WEREWOLF_LOG_OUTPUT=stderr
WEREWOLF_DJANGO_DEBUG=true
WEREWOLF_DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
OPENAI_API_KEY=
```

機密情報を含む `.env` は Git にコミットしません。
Django / LLM / ログの基本設定は `backend/src/werewolf_agent/config.py` に集約し、CLI と API の両方から同じ値を参照します。
`WEREWOLF_LOG_FORMAT` は `json` または `console`、`WEREWOLF_LOG_OUTPUT` は `stderr` または `stdout` を指定できます。

API 層や LLM 連携を触るときは、必要な optional dependencies を追加します。

```bash
uv sync --group dev --extra api
uv sync --group dev --extra llm
```

Django API のローカル確認:

```bash
uv run --extra api python backend/manage.py migrate
uv run --extra api python backend/manage.py check
uv run --extra api pytest tests/test_api_health.py
uv run --extra api python backend/manage.py runserver
```

起動後、health endpoint を確認します。

```text
http://127.0.0.1:8000/api/health/
```

Django の実装コードは `backend/src/werewolf_agent/interfaces/api/` 配下に置きます。`backend/manage.py` は Django 標準の操作入口として残します。Django app を追加する場合は、作成先ディレクトリを先に用意して target path を指定します。

```bash
cd backend
mkdir src/werewolf_agent/interfaces/api/<app_name>
uv run --extra api python manage.py startapp <app_name> src/werewolf_agent/interfaces/api/<app_name>
```

## 実行例

CLI 実装後は、以下のようなコマンドでゲームを開始できるようにする予定です。

```bash
uv run werewolf-agent play --players 6 --wolves 1 --model gpt-4.1-mini
```

ログを保存する例:

```bash
uv run werewolf-agent play --config examples/basic-game.toml --log runs/game-001.jsonl
```

## ゲーム進行

標準的な人狼ゲームに近い流れを採用します。

1. 参加者と役職を初期化する
2. 夜フェーズで人狼の襲撃、占い師の占い、騎士の護衛を処理する
3. 昼フェーズで各プレイヤーがチャット形式で発言する
4. 投票で追放者を決定する
5. 勝敗条件を確認する
6. 勝敗が決まるまで 2〜5 を繰り返す

## LLM エージェントの基本契約

エージェントは、与えられた観測情報に対して、定義済みの行動を返します。

例:

```json
{
  "speech": "昨日の投票を見ると、Alice さんの投票理由が少し薄いと感じました。",
  "vote": "Alice",
  "reason": "発言内容と投票先に一貫性がないため"
}
```

役職やフェーズによって、利用可能な行動は制限されます。

## 開発方針

- ルール処理はユニットテストを厚めに書く
- LLM 呼び出しはモック可能にする
- プロンプトはコードから分離し、バージョン管理する
- ランダム性には seed を渡せるようにする
- ログからゲームを再現できるようにする
- 人間が読める会話ログと、機械処理しやすい JSONL ログの両方を残す
- ドキュメントは、途中参加した人間や AI がすぐ再開できる形に保つ

開発メモと handoff の書き方は [docs/development.md](docs/development.md) を参照してください。

## テスト

標準の検証コマンドです。

```bash
uv run werewolf-agent doctor
uv run --extra api python backend/manage.py check
uv run --extra api pytest tests/test_api_health.py
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy backend/src
```

## ロードマップ

- [ ] ドメインモデルの実装
- [ ] ダミーエージェントの実装
- [ ] CLI での 1 ゲーム実行
- [ ] JSONL ログ出力
- [ ] LLM プロバイダー接続
- [ ] プロンプトテンプレート管理
- [ ] リプレイ機能
- [ ] Web UI
- [ ] 複数モデルの比較評価

## ライセンス

MIT License
