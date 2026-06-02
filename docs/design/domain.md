# Domain

この文書は、Sphinx で公開する完成版の domain 設計書です。
作業途中の判断、handoff、未確定メモは `docs/notes/` に置きます。

`werewolf_agent.domain` は game と LLM decision の bounded context を置く入れ物です。
`domain.game` は人狼ゲームの deterministic core です。
同じ config、players、seed、action なら同じ snapshot と event になります。
`domain.llm` は provider 非依存の agent 観測 DTO、意思決定 DTO、agent profile、LangChain provider を持ちます。

## 持つもの

- role definition、local rule flag、phase、player status
- speech、vote、night action を表す構造化 `Action`
- observer ごとの `Observation`
- phase transition
- win condition
- visibility 付き `DomainEvent`
- MLflow-compatible prompt 定義値を LangChain prompt に変換する provider
- LLM だけに渡す agent profile catalog
- LangChain output を `AgentDecision` に検証する provider

## 持たないもの

- `.env` / `get_settings()`
- ORM model / HTTP DTO
- DB
- logging 設定
- 認証
- game id、definition id などの業務識別子
- interface / usecase 呼び出し
- MVP の 5〜8 人制約など product / interface 固有の制約

## 定義体

運用で自然に差し替わるものだけを定義体にします。UI 入力や game run ごとの入力値は定義体にしません。

| 定義体 | 既定リソース | 渡す先 | 内容 |
| --- | --- | --- | --- |
| ルール定義体 | `resources/game/rules.toml` | `domain.game` | ローカルルールの有効 / 無効 |
| ロール定義体 | `resources/game/roles.toml` | `domain.game` | role ごとの faction / ability と player count 別の既定 role count |
| Scenario catalog 定義体 | `resources/game/catalog.toml` | `usecase.internal` / `domain.llm` | シナリオ、公開ナレーション、設定プリセット、能力表示 |
| Player 定義体 | `resources/llm/players.toml` | `domain.llm` | LLM に渡す名前、年齢、性別、性格、話し方、推論傾向 |
| Prompt 定義体 | `resources/prompts/agent_decision.toml` | `domain.llm` | LLM decision provider の prompt metadata / messages |
| Fake response 定義体 | `resources/llm/fake_responses.toml` | `domain.llm` | LangChain `FakeListLLM` 用 response fixture |

`game` 用定義体と `llm` 用定義体は混在させません。`domain.game` には agent profile を渡さず、`domain.llm` には game rule / role catalog を渡しません。

定義体ファイルの path 解決と TOML 読み込みは `interface/runtime` の共通 loader に集約します。定義体は `AppSettings` 構築時に通常設定と同じタイミングで検証します。`interface/application` は runtime が読み込んだ `GameDefinitions` / `LlmDefinitions` の値だけを `usecase.jobs` へ注入します。`usecase.internal.definitions` は値を domain 型へ変換するだけで、file I/O、packaged fallback、path 解決は行いません。domain / usecase は具体 agent type、role id、local rule の default を補完しません。後方互換 fallback や旧形式 migration は持ちません。

## 公開境界

外側が参照してよい domain module は次だけです。

- `werewolf_agent.domain.game.models`
- `werewolf_agent.domain.game.service`
- `werewolf_agent.domain.llm.models`
- `werewolf_agent.domain.llm.ports`
- `werewolf_agent.domain.llm.service`

`domain.game.rules` は内部実装です。
`domain.game` と `domain.llm` は互いに import しません。
両者の接続、game observation から llm observation への変換、llm decision から game action への変換は `usecase.internal` が担当します。
`interface/api` と `interface/entrypoint/cui` は domain を直接 import しません。
interface 層から usecase を呼ぶ場所は `interface/application` に限定し、呼び出し先は `usecase.jobs` の top-level 公開面だけにします。
`usecase.jobs` は domain を import せず、facade、command / query、repository / telemetry port、application bridge が必要とする永続化 contract に限定します。
domain へ入る usecase code は `usecase.internal` 配下に限定します。

この境界は `tests/unit/architecture/test_architecture_boundaries.py` で検査します。

## game 主要型

| 型 | 意味 |
| --- | --- |
| `LocalRules` | local rule flag をまとめた game 用定義体 |
| `RoleDefinition` / `RoleCatalog` | role ごとの faction と ability をまとめた game 用定義体 |
| `GameConfig` | player count、role count、解決済み `LocalRules`、`RoleCatalog` |
| `Player` | setup、snapshot、observation で共通して使う player 表現 |
| `Action` | `speech`、`vote`、`werewolf_attack`、`seer_inspect`、`knight_guard`、`pass` をまとめた構造化 action |
| `GameSnapshot` | 永続化できる完全状態 |
| `PendingActions` | 投票や夜行動のように phase 解決まで保留する action |
| `Observation` | 1 player に見せてよい情報 |
| `GameHistory` | 発話、投票結果、夜結果の append-only history |
| `DomainEvent` | 保存・公開・redaction される event の元データ |

## game 主要 service

| 関数 | 意味 |
| --- | --- |
| `start_game(config, players, rng)` | 初期 snapshot と開始 event を返す |
| `observe(snapshot, player_id)` | 1 player の observation を返す |
| `submit_action(snapshot, pending, action)` | action を検証し、snapshot / pending / event を返す |
| `advance_phase(snapshot, pending, rng)` | phase を 1 つ進め、snapshot / pending / event を返す |

## llm 主要型 / service

| 型 / 関数 | 意味 |
| --- | --- |
| `AgentObservation` | LLM provider に渡せる provider 非依存の可視情報 |
| `PlayerProfile` / `PlayerProfileCatalog` | LLM provider だけに渡す名前、年齢、性別、性格、話し方、推論傾向 |
| `AgentDecision` | LLM provider が返す構造化 decision |
| `AgentObservation.speeches` / `vote_rounds` | LLM に渡してよい公開履歴 |
| `LangChainDecisionProvider` | prompt、LangChain model、Pydantic parser をつなぐ provider |
| `LlmDecisionProvider` | real / fake provider を差し替える port |

## 進行

```text
start_game -> night -> day_discussion -> voting -> night -> ... -> finished
```

- 夜: 人狼は村側を襲撃、占い師は検査、騎士は護衛
- 昼: 生存者が `Action.speech(...)` を出す
- 投票: 生存者が `Action.vote(...)` を出す
- 勝敗: 人狼全滅で村勝利、生存人狼数が生存村側数以上で人狼勝利

同票は `no_elimination` または `random_elimination`。
自投票、投票修正、夜行動修正、初日襲撃、同票処理、護衛 / 検査の細部は `LocalRules` で制御します。各 flag の値はルール定義体で必須にし、domain は不足値を補完しません。

## Observation

`Observation` は observer ごとに生成します。

- 自分の role は見える
- 人狼は仲間の人狼を知る
- 占い師は自分の検査結果だけを知る
- 公開 speech / vote history は見える
- 他 role、夜行動、private event、debug event は見えない

API は `GameSnapshot` をそのまま返しません。
`usecase.internal` が public state / public timeline の業務 payload に変換し、
interface が HTTP / CLI / 画面向け schema に整えます。

## 乱数

乱数は外側から `random.Random` を注入します。
seed は role assignment と tie break に使います。

## 拡張先

- 新 role / rule: `resources/game/*.toml`、`commons.shared.definitions`、`domain.game.models`、`domain.game.rules`
- 新 player profile / prompt / fake response: `resources/llm/*.toml`、`resources/prompts/*.toml`、`commons.shared.definitions`
- LLM provider 非依存の decision 型: `domain.llm.models`
- Prompt / LangChain provider: `domain.llm.service`
- LLM provider adapter port: `domain.llm.ports`
- 公開 usecase facade / command / repository port: `usecase.jobs` の top-level API
- usecase workflow / projection / domain adapter: `usecase.internal`
- 複数 human / external agent action API: `usecase` に要件を置き、`interface/application` は接続、`interface/api` は入出力に寄せる

## 検証

```bash
uv run pytest tests/unit/domain
uv run pytest tests/unit/architecture/test_architecture_boundaries.py
```
