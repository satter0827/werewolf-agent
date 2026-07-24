# 開発メモ

## 目的

ゲームルールを外部サービスから独立したヘッドレスコアとして保ち、運用上変わる値を検証済み設定として注入します。画面、永続化、LLMはdomainの外側で接続します。

## 現在地

- `Game`を唯一の集約ルートとし、`submit()`と`advance()`へ状態変更を限定した
- `GameState`を不変スナップショット、遷移結果を型付きイベントへ統一した
- 未解決行動を`GameState`へ含め、`Game.restore(state, rules=...)`だけで復元できるようにした
- 行動、解決、フェーズ、勝敗、可視性をステートレスなポリシーへ分離した
- `domain/game`を`domain`直下へ展開し、`domain/llm`を削除した
- `usecase/jobs`と`usecase/internal`を廃止し、公開関数、DTO、portへ整理した
- LLMを`agents`、LangChain実装を`agents/langchain`へ分離した
- fake providerをLangChain標準`FakeListLLM`へ統一した
- `api`を`adapters`、`entrypoint`を`interfaces`へ変更した
- `commons`を`configuration`、`observability`、`security`へ分割した
- `backend`を廃止し、Python packageをトップレベルの`src`へ移した
- ポリシー構成、フェーズ順序、能力の開始日と対象条件を設定からdomainへ注入した
- 画面とLLMの対象候補計算を削除し、domainが返す合法対象へ統一した
- usecaseのテレメトリー出力を削除し、ログをinterfacesとadaptersへ限定した
- LLM provider設定とtrace sinkをusecaseから除外し、adapter側の`AgentRuntime`へ移した
- usecaseの公開面をcontext-first関数と直接利用するcommand、query、resultへ限定した
- 既定プリセットを定義順から選ぶ処理を廃止し、`game_default_setup_preset_id`から解決するようにした
- 役職、能力、シナリオ、ナレーション、プリセット間の参照を設定ロード時に検証するようにした
- 投票提出を非公開イベントに変更し、公開履歴には解決後の投票結果だけを残した
- DBスキーマ、migration、Supabase保存方式は変更していない

## 配置

| Path | 責務 |
| --- | --- |
| `src/werewolf_agent/domain/` | 集約、状態、イベント、ポリシー、公開ゲームAPI |
| `src/werewolf_agent/usecase/` | command、query、result、handler、repository port |
| `src/werewolf_agent/agents/` | provider非依存の観測、意思決定、player port |
| `src/werewolf_agent/agents/langchain/` | LangChain、LangGraph、FakeListLLM |
| `src/werewolf_agent/adapters/` | GameClient、usecase bridge、外部サービスadapter |
| `src/werewolf_agent/adapters/agents/` | agentsとusecaseを接続するgame driver |
| `src/werewolf_agent/adapters/supabase/` | Auth、Data API、worker、repository、trace sink |
| `src/werewolf_agent/interfaces/` | CLI、Streamlit、worker |
| `src/werewolf_agent/configuration/` | settings、TOML、resource検証 |
| `src/werewolf_agent/observability/` | loggingと実行context |
| `src/werewolf_agent/security/` | redaction |
| `src/werewolf_agent/contracts/` | 外部wire schemaと安全なerror |

## 設定

| 定義 | 既定ファイル | override |
| --- | --- | --- |
| ルールとポリシー構成 | `resources/game/rules.toml` | `WEREWOLF_GAME_RULES_FILE` |
| 役職と陣営 | `resources/game/roles.toml` | `WEREWOLF_GAME_ROLES_FILE` |
| 能力 | `resources/game/abilities.toml` | `WEREWOLF_GAME_ABILITIES_FILE` |
| 背景、表示名、説明 | `resources/presentation/catalog.toml` | `WEREWOLF_GAME_CATALOG_FILE` |
| 既定プリセット | `resources/settings/defaults.toml` | `WEREWOLF_GAME_DEFAULT_SETUP_PRESET_ID` |
| LLM players | `resources/llm/players.toml` | `WEREWOLF_LLM_PLAYERS_FILE` |
| decision graph | `resources/llm/decision_graphs.toml` | `WEREWOLF_LLM_DECISION_GRAPHS_FILE` |
| fake応答 | `resources/llm/fake_responses.toml` | `WEREWOLF_LLM_FAKE_RESPONSES_FILE` |
| prompt | `resources/prompts/agent_decision.toml` | `WEREWOLF_LLM_PROMPT_FILE` |

TOMLと環境変数は`configuration`だけが読みます。domainへは`RuleSetDefinition`、usecaseへは不変の`UsecaseContext`を注入します。

## 依存制約

- domainは他層へ依存しない
- usecaseはdomainと外部契約だけを使い、agentsとadaptersへ依存しない
- agentsはdomainとusecaseへ依存しない
- 自動プレイヤー接続は`adapters/agents/game_driver.py`だけに置く
- interfacesは`GameClient`経由で操作する
- domainとusecaseはlogging、DB、file I/Oを行わない
- 循環参照、import許可、外部ライブラリ配置、公開面は構造テストで固定する

## 実行コマンド

依存関係:

```bash
uv sync --group dev --extra worker --extra streamlit --extra llm
```

ローカルSupabaseとfake provider:

```bat
scripts\preflight-supabase.cmd
scripts\run-worker.cmd
scripts\run-cli.cmd play --role-count werewolf=1 --role-count seer=1 --role-count knight=1 --role-count villager=3 --seed 1
```

Supabase worker:

```bat
scripts\preflight-supabase.cmd
scripts\run-worker.cmd
```

Streamlit:

```bat
scripts\run-streamlit.cmd
```

全検証:

```bat
scripts\check-all.cmd --keep-going
```

個別検証:

```bash
uv run --no-sync pytest
uv run --no-sync ruff check --no-cache .
uv run --no-sync ruff format --check .
uv run --no-sync ruff check --no-cache --select D --ignore D100,D104 src/werewolf_agent
uv run --no-sync mypy --no-incremental src
uv run --group docs --extra streamlit sphinx-build -b html -c docs/sphinx docs docs/sphinx/_build/html
```

## 検証結果

- pytest: 232件成功
- Ruff lint: 成功
- Ruff docstring lint: 成功
- Ruff format check: 成功
- mypy: 成功
- Sphinx warning-as-error build: 成功

pytestでは、LangGraph内部の`BaseCache`が既定serializerを生成する際に
`LangChainPendingDeprecationWarning`が1件発生します。プロジェクト側の
serializer生成箇所ではないため、警告を隠す設定は追加していません。

## 削除した構造

- `domain/game`
- `domain/llm`
- `usecase/jobs`
- `usecase/internal`
- `api`
- `entrypoint`
- `commons`
- `backend`
- 旧FastAPI・Alembic起動スクリプト
- `GameService`
- `GameApi`
- 独自fake LLM
- 旧import aliasと互換export

## 未実装

- 実providerの長時間QAと評価基盤
- 複数manual player
- React UIのproduction QA
- 登録済み以外の新しい集計、勝敗、可視性アルゴリズム

## 次の一手

1. 実providerごとの契約テストを追加する
2. 設定組み合わせのproperty-based testを拡充する
3. Game集約の公開APIだけを使うシミュレーション例を追加する
