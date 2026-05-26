# Domain 設計

## 目的

`werewolf_agent.domain` は人狼ゲームの deterministic core です。
同じ設定、同じ seed、同じ action なら同じ結果になります。

## 境界

domain が持つもの:

- 役職、フェーズ、プレイヤー状態
- 投票、夜行動、発話 action
- 観測情報 `Observation`
- フェーズ遷移
- 勝敗判定
- domain event の生成

domain が持たないもの:

- `.env` / `get_settings()`
- Django model / HTTP DTO
- LLM provider 呼び出し
- ファイル I/O
- logging 設定
- 認証

## 公開モデル

外部層は `from werewolf_agent.domain import ...` を使います。
`_rules.py` などの `_` 付き module は private 実装です。

主要型:

- `GameConfig`: player count、role count、seed、投票 rule
- `GameSnapshot`: 永続化可能な完全状態
- `Observation`: 1 プレイヤーに見せてよい情報
- `SpeechAction` / `VoteAction` / `NightAction`: 構造化 action
- `DomainEvent`: 外側が保存・公開・redaction する event

## 進行

```text
Game.start
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

- 生存者が `SpeechAction` を出す
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

API は `GameSnapshot` をそのまま返しません。
公開 DTO へ変換して、role や private state を落とします。

## 乱数

乱数は外から `random.Random` を注入します。
seed は role assignment、tie break、dummy agent の選択に使います。

## テスト

中心テスト:

- `tests/test_domain_game.py`
- `tests/test_fake_llm_agent.py`
- `tests/test_api_games.py`

基本コマンド:

```bash
uv run pytest tests/test_domain_game.py tests/test_fake_llm_agent.py
uv run pytest
```

## 次に拡張する場所

- 新 role / rule: domain model と private rule module
- LLM agent: `agents` / `llm`
- 人間 action API: `interfaces/api`。domain へは構造化 action だけを渡す
- replay / evaluation: `commons.events.*` / `commons.security.redaction`
