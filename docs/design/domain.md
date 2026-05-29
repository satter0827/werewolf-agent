# Domain

この文書は、Sphinx で公開する完成版の domain 設計書です。
作業途中の判断、handoff、未確定メモは `docs/notes/` に置きます。

`werewolf_agent.domain` は game と LLM decision の bounded context を置く入れ物です。
`domain.game` は人狼ゲームの deterministic core です。
同じ config、players、seed、action なら同じ snapshot と event になります。
`domain.llm` は provider 非依存の agent 観測 DTO、意思決定 DTO、LangChain provider、prompt loader を持ちます。

## 持つもの

- role、phase、player status
- speech、vote、night action を表す構造化 `Action`
- observer ごとの `Observation`
- phase transition
- win condition
- visibility 付き `DomainEvent`
- MLflow-compatible prompt file を LangChain prompt に変換する loader
- LangChain output を `AgentDecision` に検証する provider

## 持たないもの

- `.env` / `get_settings()`
- ORM model / HTTP DTO
- DB
- logging 設定
- 認証
- interface / usecase 呼び出し
- MVP の 5〜8 人制約など product / interface 固有の制約

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
interface 層から usecase を呼ぶ場所は `interface/application` に限定し、呼び出し先は `usecase.jobs` の top-level facade だけにします。
`usecase.jobs` は domain を import せず、公開 DTO と stateless facade に限定します。
domain へ入る usecase code は `usecase.internal` 配下に限定します。

この境界は `tests/unit/architecture/test_architecture_boundaries.py` で検査します。

## game 主要型

| 型 | 意味 |
| --- | --- |
| `GameConfig` | player count、role count、seed、投票 rule |
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
| `AgentDecision` | LLM provider が返す構造化 decision |
| `AgentObservation.speeches` / `vote_rounds` | LLM に渡してよい公開履歴 |
| `PromptResource` | MLflow Prompt Registry を意識した local prompt metadata / messages |
| `FakeResponseResource` | LangChain `FakeListLLM` 用の local response fixture |
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
自投票は `allow_self_vote` で制御します。

## Observation

`Observation` は observer ごとに生成します。

- 自分の role は見える
- 人狼は仲間の人狼を知る
- 占い師は自分の検査結果だけを知る
- 公開 speech / vote history は見える
- 他 role、夜行動、private event、debug event は見えない

API は `GameSnapshot` をそのまま返しません。
`usecase.internal` が public state / public event の業務 payload に変換し、
interface が HTTP / CLI / 画面向け schema に整えます。

## 乱数

乱数は外側から `random.Random` を注入します。
seed は role assignment と tie break に使います。

## 拡張先

- 新 role / rule: `domain.game.models`、`domain.game.rules`
- LLM provider 非依存の decision 型: `domain.llm.models`
- Prompt / LangChain provider: `domain.llm.service`
- LLM provider adapter port: `domain.llm.ports`
- 公開 usecase facade / DTO / repository port: `usecase.jobs` の top-level API
- usecase workflow / projection / domain adapter: `usecase.internal`
- 複数 human / external agent action API: `usecase` に要件を置き、`interface/application` は接続、`interface/api` は入出力に寄せる

## 検証

```bash
uv run pytest tests/unit/domain
uv run pytest tests/unit/architecture/test_architecture_boundaries.py
```
