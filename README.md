# Werewolf Agent

LLM agentを人狼ゲームのプレイヤーとして動かすPython backendです。ゲームの真実はdeterministicなヘッドレスコアが管理し、画面、LLM、Supabaseは外側から接続します。

## 現在地

- domain単体でゲーム作成、行動受付、フェーズ進行、勝敗判定を実行できる
- ルールはステートレスなポリシーと検証済み設定の組み合わせで構成する
- usecaseはIDを含む利用者要求とdomainを接続するステートレス関数である
- LLMは独立した`agents`に置き、LangChain標準の`FakeListLLM`で外部APIなしに動作する
- CLIとStreamlitは`GameClient`経由でSupabase Data APIへ接続する
- 公開状態、公開履歴、LLM入力、運用ログから秘密情報を分離する

## 起動

依存関係を同期します。

```bash
uv sync --group dev --extra llm --extra streamlit --extra worker
```

ローカルSupabaseを準備し、外部LLMを使わず`FakeListLLM`で1ゲーム実行します。

```bat
scripts\preflight-supabase.cmd
scripts\run-worker.cmd
scripts\run-cli.cmd play --role-count werewolf=1 --role-count seer=1 --role-count knight=1 --role-count villager=3 --seed 1
```

環境変数を設定済みの場合は、CLIを直接実行できます。

```bash
uv run werewolf-agent play --role-count werewolf=1 --role-count seer=1 --role-count knight=1 --role-count villager=3 --seed 1
```

Streamlitを起動します。

```bat
scripts\preflight-supabase.cmd
scripts\run-streamlit.cmd
```

workerを起動します。

```bat
scripts\run-worker.cmd
```

Supabaseを手動で準備する場合:

```bash
supabase start
supabase status -o env
supabase migration up
uv run --extra worker werewolf-agent-worker run
```

## 構成

| Path | 責務 |
| --- | --- |
| `src/werewolf_agent/domain/` | ゲーム集約、状態、イベント、ルールポリシー |
| `src/werewolf_agent/usecase/` | command、query、result、handler、repository port |
| `src/werewolf_agent/agents/` | player agent契約、観測、意思決定 |
| `src/werewolf_agent/agents/langchain/` | LangChain、LangGraph、FakeListLLM |
| `src/werewolf_agent/adapters/` | GameClient、外部サービス、usecase bridge |
| `src/werewolf_agent/interfaces/` | CLI、Streamlit、worker |
| `src/werewolf_agent/configuration/` | settings、TOML、resource読込 |
| `src/werewolf_agent/observability/` | loggingと実行context |
| `src/werewolf_agent/security/` | 秘密情報のredaction |
| `src/werewolf_agent/contracts/` | 外部wire schemaと安全なerror |
| `src/werewolf_agent/resources/` | game、presentation、LLM、promptの既定設定 |

依存方向は外側から内側への一方向です。

```text
interfaces -> adapters -> usecase -> domain
                    \-> agents
```

agentsとdomainは互いに参照しません。`adapters/agents/game_driver.py`が観測と行動を変換し、domainが合法性を最終判断します。

## Domain

domainの公開面は次に限定しています。

```python
from werewolf_agent.domain import (
    Action,
    Game,
    GameEvent,
    GameSetup,
    GameState,
    GameView,
    RuleRegistry,
    RuleSet,
    RuleSetDefinition,
    RuleViolation,
)
```

`Game`だけが状態を変更します。`GameState`は未解決行動を含む完全な不変スナップショットで、不正行動や必須行動不足では状態を変更せず`RuleViolation`を返します。ランダム源は外部から注入するため、同じseedと入力から同じイベント列を再現できます。

詳細は[Domain設計](docs/design/domain.md)を参照してください。

## Usecase

usecaseはモジュールレベル関数と不変の`UsecaseContext`を公開します。

```python
create_game(context, command)
submit_player_action(context, command)
advance_game(context, command)
get_game(context, query)
get_player_observation(context, query)
```

repositoryから取得し、domainを復元し、公開操作を呼び、結果をDTOへ変換します。役職、フェーズ、勝敗、対象条件のゲームルールは実装しません。
LLM provider設定とtrace sinkはusecaseへ持ち込まず、`adapters/agents/game_driver.py`が管理します。

## 設定

| ファイル | 変更できること |
| --- | --- |
| `resources/game/rules.toml` | 提出回数、自己対象、再提出、同票処理、ポリシー構成 |
| `resources/game/roles.toml` | 役職、陣営、能力、既定人数 |
| `resources/game/abilities.toml` | 利用フェーズ、対象条件、解決ポリシー、開始日 |
| `resources/presentation/catalog.toml` | 背景、シナリオ、表示名、説明 |
| `resources/llm/` | player、decision graph、fake応答 |
| `resources/prompts/` | prompt |
| `resources/settings/defaults.toml` | provider、timeout、retry、model、運用上限 |

登録済みポリシーの組み合わせとパラメーターは設定だけで変更できます。新しい集計、状態遷移、能力効果、勝敗、可視性アルゴリズムはPython実装と`RuleRegistry`への明示登録が必要です。

既定の画面プリセットは`WEREWOLF_GAME_DEFAULT_SETUP_PRESET_ID`で選択します。役職から能力、シナリオからナレーション、プリセットからシナリオと役職への参照は、設定ロード時にまとめて検証します。

外部ファイルで上書きする場合は`.env.example`の`WEREWOLF_*_FILE`を参照してください。関連する定義ファイルは整合する組み合わせで指定します。TOMLと環境変数は`configuration`だけが読み、domainへは検証済みの値だけを渡します。

## LLM

既定providerは外部ネットワークを使わない`fake`です。

```text
WEREWOLF_LLM_PROVIDER=fake
WEREWOLF_MODEL=fake-list-llm
```

LM Studio:

```text
WEREWOLF_LLM_PROVIDER=lmstudio
WEREWOLF_MODEL=auto
WEREWOLF_LLM_BASE_URL=http://127.0.0.1:1234/v1
```

OpenAI:

```text
WEREWOLF_LLM_PROVIDER=openai
WEREWOLF_MODEL=gpt-4.1-mini
OPENAI_API_KEY=<secret>
```

fakeと実providerはprompt、構造化出力、検証、再試行、fallbackを共有します。LLMはdomainが提示した合法対象から候補行動を返し、提出時の合法性もdomainが再検証します。

## ログ

domainとusecaseはログを出しません。interfacesとadaptersが外部境界で一度だけ記録します。通常の入力不備、存在しないID、ルール違反はエラーログではなく結果として扱います。

ログはJSON Linesで、workerは`worker.jsonl`、Streamlitは`streamlit.jsonl`、CLIは`cli.jsonl`、migrationは`migrate.jsonl`を使用します。役職、夜行動、対象、秘密状態、prompt、LLM生出力、認証情報は出力しません。投票先も集計完了までは公開履歴へ出しません。

## 検証

```bat
scripts\check-all.cmd --keep-going
```

個別に実行する場合:

```bash
uv run --no-sync pytest
uv run --no-sync ruff check --no-cache .
uv run --no-sync ruff format --check .
uv run --no-sync ruff check --no-cache --select D --ignore D100,D104 src/werewolf_agent
uv run --no-sync mypy --no-incremental src
uv run --group docs --extra streamlit sphinx-build -b html -c docs/sphinx docs docs/sphinx/_build/html
```

構造テストは層ごとのimport許可、モジュール循環、層循環、外部ライブラリ配置、公開`__all__`、旧構造不在を検査します。

## 文書

- [Domain設計](docs/design/domain.md)
- [境界と公開契約](docs/design/api.md)
- [Agent strategy](docs/design/agent-strategies.md)
- [開発メモ](docs/notes/development.md)

## 未実装

- 実providerの長時間QAと評価基盤
- 複数manual player
- React UIのproduction QA

## License

MIT License
