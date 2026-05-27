# Domain

`werewolf_agent.domain` は人狼ゲームの deterministic core です。
同じ config、players、seed、action なら同じ snapshot と event になります。

## 持つもの

- role、phase、player status
- speech、vote、night action を表す構造化 `Action`
- observer ごとの `Observation`
- phase transition
- win condition
- visibility 付き `DomainEvent`
- dummy agent 用の provider 非依存 action 選択

## 持たないもの

- `.env` / `get_settings()`
- ORM model / HTTP DTO
- DB / file I/O
- logging 設定
- 認証
- LLM provider 呼び出し
- MVP の 5〜8 人制約など product / interface 固有の制約

## 公開境界

外側が参照してよい domain module は次だけです。

- `werewolf_agent.domain.models`
- `werewolf_agent.domain.service`

`domain.rules` は内部実装です。
`interface/api` と `interface/cui` は domain を直接 import しません。
interface 層から usecase を呼ぶ場所は `interface/application` に限定します。

この境界は `tests/unit/architecture/test_architecture_boundaries.py` で検査します。

## 主要型

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

## 主要 service

| 関数 | 意味 |
| --- | --- |
| `start_game(config, players, rng)` | 初期 snapshot と開始 event を返す |
| `observe(snapshot, player_id)` | 1 player の observation を返す |
| `submit_action(snapshot, pending, action)` | action を検証し、snapshot / pending / event を返す |
| `advance_phase(snapshot, pending, rng)` | phase を 1 つ進め、snapshot / pending / event を返す |
| `choose_dummy_action(player_id, observation, rng)` | dummy agent 用の deterministic action を返す |

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
`usecase.internals.projections` が public state / public event に変換します。

## 乱数

乱数は外側から `random.Random` を注入します。
seed は role assignment、tie break、dummy agent の選択に使います。

## 拡張先

- 新 role / rule: `domain.models`、`domain.rules`
- 公開 workflow / port: `usecase.jobs`
- 公開 projection 内部実装: `usecase.internals.projections`
- 自動 agent の実装と選択: `usecase.jobs.agents`
- human / LLM action API: `usecase` に要件を置き、`interface/application` は接続、`interface/api` は入出力に寄せる

## 検証

```bash
uv run pytest tests/unit/domain
uv run pytest tests/unit/architecture/test_architecture_boundaries.py
```
