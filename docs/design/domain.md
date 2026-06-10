# Domain

この文書は、`domain`、`domain.llm`、`usecase` の境界を固定します。
API 詳細、UI 手順、handoff は別文書に置きます。

## 目的

- `domain.game` は人狼ゲームの deterministic core として、同じ config、seed、action から同じ snapshot と event を返す
- `domain.llm` は provider 非依存の observation / decision 契約と LangChain provider を持つ
- `usecase.internal` が game observation と LLM decision を変換し、両 domain を直接 import させない
- `commons.configuration` と `commons.resources` が設定、definition、logging を解決し、`api.usecase_bridge` から usecase へ値として注入する

## 持つもの

`domain.game`:

- role definition、local rules、phase、player status
- `speech`、`vote`、`werewolf_attack`、`seer_inspect`、`knight_guard`、`pass`
- observer ごとの observation
- phase transition、win condition、pending action
- visibility 付き domain event

`domain.llm`:

- `AgentObservation`
- `AgentDecision`
- `PlayerProfile` / `PlayerProfileCatalog`
- `LlmDecisionProvider` port
- LangChain prompt / parser / provider adapter

`usecase.jobs`:

- `GameService`
- command / query DTO
- repository / telemetry port
- API adapter が必要とする永続化 contract

## 持たないもの

- `.env` / `get_settings()`
- Streamlit / Typer
- Supabase / DB adapter
- file I/O
- logging bootstrap
- API key
- wire schema
- UI session state
- 旧形式 fallback / migration

## 定義体

| 定義体 | 既定リソース | 渡す先 | 内容 |
| --- | --- | --- | --- |
| ルール定義体 | `resources/game/rules.toml` | `domain.game` | local rule |
| ロール定義体 | `resources/game/roles.toml` | `domain.game` | faction / ability / default role counts |
| Game catalog | `resources/game/catalog.toml` | `usecase.internal` / `domain.llm` | scenario、narration、setup preset、ability label |
| LLM players | `resources/llm/players.toml` | `domain.llm` | LLM profile |
| LLM prompt | `resources/prompts/agent_decision.toml` | `domain.llm` | prompt metadata / messages |
| LLM decision graphs | `resources/llm/decision_graphs.toml` | `domain.llm` | agent strategy metadata / graph node |
| Fake responses | `resources/llm/fake_responses.toml` | `domain.llm` | `FakeListLLM` fixture |

definition path 解決と TOML 読み込みは `commons.resources` に集約します。`AppSettings` 構築時に definition を検証し、`api.usecase_bridge` が `GameDefinitions` / `LlmDefinitions` を usecase へ注入します。domain と usecase は source path、packaged default、`.env` を知りません。

## 境界

- `domain.game` と `domain.llm` は互いに import しない
- `usecase.jobs` は domain を import しない
- domain へ入る code は `usecase/internal` 配下に限定する
- `usecase/internal` は API / entrypoint / wire schema に依存しない
- CLI / Streamlit は domain / usecase を直接 import せず、`contracts` と `GameApi` port だけを使う
- `api` は `entrypoint` に依存しない
- `api` から usecase を呼ぶ場所は `api/usecase_bridge.py`、`api/setup_options.py`、`api/local_demo/`、`api/supabase/worker/`、`api/telemetry.py` に限定する
- `api/usecase_bridge.py` は `werewolf_agent.usecase.jobs` の top-level 公開面だけを import する
- `commons` は `api`、`entrypoint`、`domain`、`usecase` に依存しない

この境界は `tests/unit/architecture/test_architecture_boundaries.py` で固定します。

## Game Core

主要型:

| 型 | 意味 |
| --- | --- |
| `LocalRules` | game ごとの local rule |
| `RoleDefinition` / `RoleCatalog` | role ごとの faction / ability |
| `GameConfig` | player count、role counts、rules、role catalog |
| `Player` | setup、snapshot、observation で使う player |
| `Action` | 構造化 game action |
| `GameSnapshot` | 永続化できる完全状態 |
| `PendingActions` | phase 解決まで保留する action |
| `Observation` | 1 player に見せてよい情報 |
| `GameHistory` | speech、vote、night result の append-only history |
| `DomainEvent` | 保存・公開・redaction の元になる event |

主要 service:

| 関数 | 意味 |
| --- | --- |
| `start_game(config, players, rng)` | 初期 snapshot と開始 event を返す |
| `observe(snapshot, player_id)` | 1 player の observation を返す |
| `submit_action(snapshot, pending, action)` | action を検証して反映する |
| `advance_phase(snapshot, pending, rng)` | phase を 1 つ進める |

local rules は game ごとの deterministic rule だけを持ちます。`day_speech_limit_per_player` は `available_actions` と `submit_action` の両方で使い、UI だけの制御にはしません。

## LLM Core

`AgentObservation` は LLM に渡せる唯一の観測 DTO です。

- `phase`、`day`
- `me`
- `role`
- visible `players`
- その player だけが知る `known_roles`
- `available_actions`
- action ごとの `legal_targets`
- public `speeches`
- public `vote_rounds`

`LangChainDecisionProvider` は `agent_strategy_id` に対応する LangGraph `StateGraph` を使い、prompt、LangChain model、Pydantic parser、validation、repair、deterministic fallback を接続します。LLM 出力は `AgentDecision` として検証し、不正 JSON、不正 action、不正 target、provider 呼び出し失敗は保存済み seed と合法 action から deterministic fallback にします。

prompt resource と graph definition は `AgentObservation` の契約だけを参照します。raw prompt、raw response、API key は public response、public timeline、operational log へ出しません。admin-only LLM trace には改善用に prompt message、prompt hash、raw response、parsed decision、graph route metadata を保存します。

## Usecase 接続

`usecase.internal` は次を担当します。

- runtime definition を domain 型へ変換する
- `GameSnapshot` を public state / public timeline へ projection する
- manual player の pending input を判定する
- `AgentObservation` に公開履歴と合法 target を入れて LLM provider へ渡す
- `AgentDecision` を domain `Action` へ変換する
- repository port に保存する payload を作る

`usecase.jobs.GameService` は API adapter 向けの最小 facade です。`api.usecase_bridge` は settings と definition を usecase 用の値へ変換し、`api.local_demo` と `api.supabase.worker` は repository / telemetry / LLM provider 設定を注入して facade を実行します。`api.setup_options` は HTTP を介さない CLI / Streamlit の開始画面 metadata だけを facade から取得します。

- `create_game`
- `get_game`
- `advance_game`
- `list_games`
- `list_timeline`
- `get_player_observation`
- `submit_player_action`
- `get_game_reveal`
- `get_setup_options`

## Observation

game observation:

- 自分の role は見える
- 人狼は仲間の人狼を知る
- 占い師は自分の検査結果だけを知る
- 公開 speech / vote history は見える
- 他 role、夜行動、private event、debug event は見えない

API は `GameSnapshot` を返しません。`usecase.internal` が public state / public timeline に変換し、`api` と `entrypoint` が CLI / 画面向け schema に整えます。

## 検証

```bash
uv run pytest tests/unit/domain
uv run pytest tests/unit/usecase
uv run pytest tests/unit/architecture/test_architecture_boundaries.py
```
