# API

Django API は CLI と将来の UI が使う公開契約です。
DB には完全状態を保存しますが、レスポンスは public state / public event だけです。

## 現在の範囲

- 同期 API
- dummy agent による自動進行
- game 作成、状態取得、1 step 進行、public event 取得
- Problem Details 形式の error response
- 認証、手動 action、private observation、SSE / WebSocket は未実装

## Endpoints

| Method | Path | 用途 |
| --- | --- | --- |
| `GET` | `/api/health/` | `{"status":"ok","service":"werewolf-agent-api"}` |
| `GET` | `/api/rulesets/default/` | player count、roles、phases、agent types |
| `POST` | `/api/games/` | game run 作成 |
| `GET` | `/api/games/{game_id}/` | public state 取得 |
| `POST` | `/api/games/{game_id}/steps/` | 現在 phase を 1 step 進める |
| `POST` | `/api/games/{game_id}/advance/` | `steps` の互換 alias |
| `GET` | `/api/games/{game_id}/events/?after=<seq>` | public event を sequence 昇順で取得 |

## Create Game

最小:

```json
{"player_count": 6, "seed": 1}
```

明示:

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

- `player_count`: 5〜8。省略時は 6
- `players`: 指定時は 5〜8 件。`id` は一意
- `agent.type` / `players[].agent_type`: 現在は `dummy` のみ
- `role_counts`: 合計が player count と一致し、人狼 1 以上、村側 1 以上
- `tie_break_policy`: `no_elimination` または `random_elimination`
- `day_speech_turns`: 1〜5

## Public State

返すもの:

- `game_id`、`status`、`phase`、`day`、`version`、`seed`
- player id / name / alive / status
- alive / eliminated player ids
- `winner`
- public summary counts
- `created_at`、`updated_at`

返さないもの:

- role assignment
- night action detail
- private observation
- `private_state`
- prompt、API key、raw provider response

## Events

`GET /events/` は `visibility == "public"` の event だけを返します。
`game_started` の `role_counts` は public payload から落とします。

Cursor:

- request: `after=<last_sequence>`
- response: `next_after`

## Errors

Error response は RFC 9457 Problem Details 互換です。
`Content-Type` は `application/problem+json`。

| Status | Code | 例 |
| --- | --- | --- |
| `400` | `request.validation_failed` | body / query validation |
| `404` | `not_found` | game が存在しない |
| `409` | `game.invalid_phase` | 終了済み game の進行 |
| `422` | `game.invalid_action` | 未対応 agent type、ルール違反 |
| `500` | `internal.unexpected` | 想定外エラー |

## 実装位置

| Path | 責務 |
| --- | --- |
| `interfaces/api/games/views.py` | endpoint |
| `interfaces/api/schemas.py` | HTTP DTO |
| `interfaces/api/games/services.py` | transaction と usecase 呼び出し |
| `interfaces/api/games/repositories.py` | Django DB adapter |
| `interfaces/api/games/models.py` | `GameRun` / `GameEventRecord` |
| `interfaces/api/errors.py` | Problem Details 変換 |
| `usecase/games.py` | game workflow |
| `usecase/models.py` | usecase DTO |
| `usecase/projections.py` | public state / event projection |

`interfaces/api` は domain を直接 import しません。

## 検証

```bash
uv run --extra api python backend/manage.py check
uv run --extra api pytest tests/integration/api
```
