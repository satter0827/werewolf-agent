# Domain

`werewolf_agent.domain` は人狼ゲームの deterministic core です。
同じ config、players、seed、action なら同じ snapshot と event になります。

## 持つもの

- role、phase、player status
- speech、vote、night action
- observer ごとの `Observation`
- phase transition
- win condition
- visibility 付き `DomainEvent`
- provider 非依存の `DummyAgent`

## 持たないもの

- `.env` / `get_settings()`
- Django model / HTTP DTO
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
`interfaces` は domain を直接 import せず、`usecase` の stateless function を呼びます。

この境界は `tests/unit/architecture/test_architecture_boundaries.py` で検査します。

## 主要型

| 型 | 意味 |
| --- | --- |
| `GameConfig` | player count、role count、seed、投票 rule |
| `PlayerConfig` | player id、name、任意の固定 role |
| `GameSnapshot` | 永続化できる完全状態 |
| `Observation` | 1 player に見せてよい情報 |
| `SpeechAction` / `VoteAction` / `NightAction` | 構造化 action |
| `DomainEvent` | 保存・公開・redaction される event の元データ |
| `Game` | snapshot を操作する state machine facade |

## 進行

```text
night -> day_discussion -> voting -> night -> ... -> finished
```

- 夜: 人狼は村側を襲撃、占い師は検査、騎士は護衛
- 昼: 生存者が `SpeechAction` を出す
- 投票: 生存者が生存者へ投票する
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
`usecase.projections` が public state / public event に変換します。

## 乱数

乱数は外側から `random.Random` を注入します。
seed は role assignment、tie break、dummy agent の選択に使います。

## 拡張先

- 新 role / rule: `domain.models`、`domain.rules`
- 公開 projection: `usecase.projections`
- 自動 agent の選択: `usecase.agents`
- human / LLM action API: `usecase` に要件を置き、`interfaces/api` は入出力に寄せる

## 検証

```bash
uv run pytest tests/unit/domain
uv run pytest tests/unit/architecture/test_architecture_boundaries.py
```
