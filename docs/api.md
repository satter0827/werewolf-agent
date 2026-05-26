# API 設計

## 目的

Django API は、CLI と将来の観戦 UI が使う公開ゲーム契約です。
内部の `GameSnapshot` は保存しますが、レスポンスには公開状態と public event だけを出します。

## 現在の範囲

- 同期 API
- dummy agent の自動進行
- ゲーム作成、状態取得、1 ステップ進行、公開イベント取得
- 役職、夜行動、debug state、private observation は非公開
- 認証、手動 action 投入、SSE / WebSocket は未実装

## Endpoints

| Method | Path | 用途 |
| --- | --- | --- |
| `GET` | `/api/health/` | 死活監視 |
| `GET` | `/api/rulesets/default/` | MVP ルールセット metadata |
| `POST` | `/api/games/` | game run 作成 |
| `GET` | `/api/games/{game_id}/` | 公開状態取得 |
| `POST` | `/api/games/{game_id}/steps/` | 現在フェーズを 1 ステップ進める |
| `POST` | `/api/games/{game_id}/advance/` | `steps` の互換 alias |
| `GET` | `/api/games/{game_id}/events/?after=<seq>` | public event を sequence 昇順で取得 |

## Create Game

最小:

```json
{"player_count": 6, "seed": 1}
```

明示指定:

```json
{
  "seed": 42,
  "agent": {"type": "dummy"},
  "rule_config": {
    "role_counts": {"werewolf": 1, "seer": 1, "knight": 1, "villager": 2},
    "tie_break_policy": "no_elimination",
    "day_speech_turns": 1,
    "allow_self_vote": false
  },
  "players": [
    {"id": "p1", "name": "Alice", "agent_type": "dummy"},
    {"id": "p2", "name": "Bob", "agent_type": "dummy"},
    {"id": "p3", "name": "Carol", "agent_type": "dummy"},
    {"id": "p4", "name": "Dave", "agent_type": "dummy"},
    {"id": "p5", "name": "Eve", "agent_type": "dummy"}
  ]
}
```

制約:

- `player_count`: 5〜8
- `agent.type`: 現在は `dummy` のみ
- `players[].agent_type`: 現在は `dummy` のみ
- `role_counts`: `villager`、`werewolf`、`seer`、`knight`。合計は player count と一致
- `tie_break_policy`: `no_elimination` または `random_elimination`
- `day_speech_turns`: 1〜5
- `allow_self_vote`: boolean

## 公開 DTO

`PublicGameState` に含めるもの:

- game id、status、phase、day、version、seed
- player id、name、生死状態
- alive / eliminated player ids
- winner
- summary count

含めないもの:

- role assignment
- night action detail
- private observation
- `GameRun.private_state`
- LLM prompt / raw provider response

## Events

public event だけを返します。
domain event の `debug` / `player_private` は保存されても公開 API では返しません。
`game_started` の role count も public payload から除去します。

## Errors

API error は RFC 9457 Problem Details (`application/problem+json`) です。

| Status | Code | 例 |
| --- | --- | --- |
| `400` | `request.validation_failed` | body / query validation |
| `404` | `not_found` | game が存在しない |
| `409` | `game.invalid_phase` | 終了済み game の進行 |
| `422` | `game.invalid_action` | 未対応 agent type、ルール違反 |
| `500` | `internal.unexpected` | 想定外エラー |

## 実装位置

- HTTP DTO: `backend/src/werewolf_agent/contracts/api.py`
- Use case DTO / workflow: `backend/src/werewolf_agent/usecase/models.py`、`backend/src/werewolf_agent/usecase/games.py`
- Problem Details schema: `backend/src/werewolf_agent/contracts/schemas.py`
- Error handler: `backend/src/werewolf_agent/interfaces/api/errors.py`
- View: `backend/src/werewolf_agent/interfaces/api/games/views.py`
- Service adapter: `backend/src/werewolf_agent/interfaces/application/games.py`
- DB repository adapter: `backend/src/werewolf_agent/interfaces/application/repositories.py`
- DB model: `backend/src/werewolf_agent/interfaces/api/games/models.py`

`interfaces/api` は domain / agents を直接 import しません。
usecase との接続は `interfaces/application` に閉じ、業務要件と公開投影は usecase に置きます。

## 確認コマンド

```bash
uv run --extra api python backend/manage.py check
uv run --extra api pytest tests/integration/api
uv run --extra api python backend/manage.py runserver
```
