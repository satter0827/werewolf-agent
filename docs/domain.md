# Domain 設計

## 目的

`werewolf_agent.domain` は人狼ゲームの deterministic core です。
同じ設定、同じ seed、同じ action なら同じ結果になります。

## 境界

domain が持つもの:

- 役職、フェーズ、プレイヤー状態
- 投票、夜行動、発話を表す構造化 `Action`
- 観測情報 `Observation`
- フェーズ遷移
- 勝敗判定
- domain event の生成
- dummy agent の deterministic action 選択

domain が持たないもの:

- `.env` / `get_settings()`
- Django model / HTTP DTO
- LLM provider 呼び出し
- ファイル I/O
- logging 設定
- 認証
- MVP の 5〜8 人制約など interface / product 固有の業務要件

## 公開境界

interface から domain を使う経路は `werewolf_agent.usecase` だけです。
usecase は `werewolf_agent.domain.models` と `werewolf_agent.domain.service` だけを使います。
interface 層は domain を直接 import せず、usecase のステートレス関数を呼びます。
`werewolf_agent.domain.rules` は domain 内部の実装です。

責務:

- `models.py`: headless 利用者が扱う domain model と enum
- `service.py`: snapshot / pending action を受け取るステートレス関数
- `rules/`: `models` と `service` が使う内部処理

主要型:

- `GameConfig`: player count、role count、seed、投票 rule
- `Player`: setup、snapshot、observation で共通して使う player 表現
- `Action`: `speech`、`vote`、`werewolf_attack`、`seer_inspect`、`knight_guard`、`pass` をまとめた構造化 action
- `GameSnapshot`: 永続化可能な完全状態
- `PendingActions`: 投票や夜行動のように phase 解決まで保留する action
- `Observation`: 1 プレイヤーに見せてよい情報
- `DomainEvent`: 外側が保存・公開・redaction する event
- `GameHistory`: 発話、投票結果、夜結果の append-only history

主要 service:

- `start_game(config, players, rng)`: 初期 snapshot と開始 event を返す
- `observe(snapshot, player_id)`: 1 player の observation を返す
- `submit_action(snapshot, pending, action)`: action を検証し、snapshot / pending / event を返す
- `advance_phase(snapshot, pending, rng)`: phase を 1 つ進め、snapshot / pending / event を返す
- `choose_dummy_action(player_id, observation, rng)`: dummy agent 用の deterministic action を返す

## 進行

```text
start_game
  -> night
  -> day_discussion
  -> voting
  -> night ...
  -> finished
```

夜:

- 人狼は村側だけを襲撃できる
- 占い師は自分以外を占える
- 騎士は生存者を護衛できる
- 襲撃先と護衛先が一致すれば死亡なし

昼:

- 生存者が `Action.speech(...)` を出す
- API 側では `day_speech_turns` 回、生存者を巡回する

投票:

- 生存者が生存者へ投票する
- 自投票は `allow_self_vote` で制御
- 同票は `no_elimination` または `random_elimination`

勝敗:

- 人狼が全滅: 村側勝利
- 生存人狼数が生存村側数以上: 人狼勝利

## 情報公開

`Observation` は observer ごとに作ります。

- 自分の role は見える
- 人狼は仲間の人狼を知る
- 占い師は自分の占い結果だけを知る
- 公開 speeches / vote history は見える
- 他 role、夜行動、debug event は見えない

usecase / API は `GameSnapshot` をそのまま返しません。
公開 DTO へ変換して、role や private state を落とします。

## 乱数

乱数は外から `random.Random` を注入します。
seed は role assignment、tie break、dummy agent の選択に使います。

## テスト

中心テスト:

- `tests/unit/domain/test_domain_game.py`
- `tests/unit/domain/test_dummy_agent.py`
- `tests/integration/api/test_api_games.py`

基本コマンド:

```bash
uv run pytest tests/unit/domain/test_domain_game.py tests/unit/domain/test_dummy_agent.py
uv run pytest
```

## 次に拡張する場所

- 新 role / rule: `domain.models` と `domain.rules`
- LLM agent: `llm` と usecase の agent port
- 人間 action API: `usecase` に業務要件を置き、`interfaces/api` は HTTP 入出力だけを扱う
- replay / evaluation: `commons.events.*` / `commons.security.redaction`
