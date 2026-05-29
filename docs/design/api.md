# API

この文書は、Sphinx で公開する完成版の API 設計書です。
作業途中の判断、handoff、未確定メモは `docs/notes/` に置きます。

FastAPI は CLI と将来の UI が使う公開契約です。DB には完全状態を保存しますが、
レスポンスは public state / public event だけです。

## 現在の範囲

- 同期 REST API
- public event SSE
- `llm` agent と LangChain `fake` provider による自動進行
- game 作成、一覧、状態取得、1 step 進行、public event、turn history 取得
- Problem Details 形式の error response
- Streamlit のプレイ画面は public API 経由で実装済み。React UI、永続 login/session 管理は未実装
- 手動 action と private observation は、作成時に返す player token で 1 人分だけ操作できる

## Endpoints

| Method | Path | 用途 |
| --- | --- | --- |
| `GET` | `/api/v1/health` | `{"status":"ok","service":"werewolf-agent-api"}` |
| `GET` | `/api/v1/rulesets/default` | player count、roles、phases、agent types |
| `POST` | `/api/v1/games` | game run 作成 |
| `GET` | `/api/v1/games?status=<status>&limit=<n>&offset=<n>` | public run summary 一覧 |
| `GET` | `/api/v1/games/{game_id}` | public state 取得 |
| `POST` | `/api/v1/games/{game_id}/steps` | 現在 phase を 1 step 進める |
| `GET` | `/api/v1/games/{game_id}/players/{player_id}/observation` | token 付き private observation |
| `POST` | `/api/v1/games/{game_id}/players/{player_id}/actions` | token 付き manual action |
| `GET` | `/api/v1/games/{game_id}/events?after=<seq>&limit=<n>` | public event を sequence 昇順で取得 |
| `GET` | `/api/v1/games/{game_id}/events/stream?after=<seq>&limit=<n>` | public event を SSE 形式で取得 |
| `GET` | `/api/v1/games/{game_id}/turns?after=<seq>&limit=<n>` | UI 向け public timeline を取得 |

## Create Game

最小:

```json
{"player_count": 6, "seed": 1}
```

明示:

```json
{
  "seed": 42,
  "agent": {"type": "llm"},
  "rule_config": {
    "role_counts": {"werewolf": 1, "seer": 1, "knight": 1, "villager": 2},
    "tie_break_policy": "no_elimination",
    "day_speech_turns": 1,
    "allow_self_vote": false
  },
  "players": [
    {"id": "p1", "name": "Alice", "agent_type": "llm"},
    {"id": "p2", "name": "Bob", "agent_type": "llm"},
    {"id": "p3", "name": "Carol", "agent_type": "llm"},
    {"id": "p4", "name": "Dave", "agent_type": "llm"},
    {"id": "p5", "name": "Eve", "agent_type": "llm"}
  ]
}
```

制約:

- `player_count`: 既定では 5〜8。省略時は `WEREWOLF_GAME_DEFAULT_PLAYER_COUNT`。実際の範囲は `WEREWOLF_GAME_MIN_PLAYERS` / `WEREWOLF_GAME_MAX_PLAYERS` で決まる
- `players`: 指定時は 5〜8 件。`id` は一意
- `agent.type`: 現在は `llm` のみ。実体 provider は `WEREWOLF_LLM_PROVIDER=fake`
- `players[].agent_type`: `llm` または `human`。`human` は 1 game につき 1 人まで
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

`GET /events` と `GET /events/stream` は `visibility == "public"` の event だけを返します。
`game_started` の `role_counts` は public payload から落とします。

## Manual Player

`players[].agent_type=human` を含む game 作成レスポンスは、作成時だけ `control_tokens` を返します。
API は token hash だけを保存し、平文 token は保存しません。

private observation と manual action は `Authorization: Bearer <token>` が必要です。
token なしは `401 auth.required`、不正 token は `403 auth.forbidden` です。

manual action body:

```json
{"type": "speech", "message": "I am checking the table."}
```

`type` は `speech`、`vote`、`werewolf_attack`、`seer_inspect`、`knight_guard`、`pass` です。
target が必要な action は `target_id` を指定します。

Cursor:

- request: `after=<last_sequence>&limit=<n>`
- response: `next_after`

SSE:

- event: `game_event`
- id: `sequence`
- data: `PublicGameEvent` JSON

## Run Summary / Turns

`GET /games` は UI の一覧画面と CLI `runs` が使う public summary だけを返します。
`GET /turns` は React / Streamlit の timeline がそのまま使える public read model です。

返すもの:

- status、phase、day、version、seed
- player_count、alive_count、winner
- step_count、turn_count
- turn sequence、event_sequence、event_type、actor_id、public payload、timestamp

返さないもの:

- role assignment
- night action target
- private observation
- raw prompt / raw provider response

## Errors

Error response は RFC 9457 Problem Details 互換です。
`Content-Type` は `application/problem+json`。
API response には `X-Trace-Id` header を付け、Problem Details の `trace_id` と対応させます。

| Status | Code | 例 |
| --- | --- | --- |
| `400` | `request.validation_failed` | body / query validation |
| `404` | `resource.not_found` | game が存在しない |
| `405` | `request.method_not_allowed` | method が未対応 |
| `409` | `game.invalid_phase` | 終了済み game の進行 |
| `422` | `game.invalid_action` | 未対応 agent type、ルール違反 |
| `500` | `internal.unexpected` | 想定外エラー |

## 実装位置

| Path | 責務 |
| --- | --- |
| `contracts/schemas.py` | HTTP wire DTO、Problem Details schema |
| `contracts/errors.py` | error code metadata |
| `interface/shared/http.py` | FastAPI Problem Details 変換 |
| `interface/api/routers.py` | endpoint |
| `interface/application/games.py` | stateless application bridge、transaction、依存注入 |
| `interface/application/repositories.py` | SQLAlchemy repository adapter |
| `interface/application/models.py` | `game_runs` / `game_events` / read model ORM |
| `usecase/jobs/` | interface 向けの薄い usecase facade、DTO、repository port |
| `usecase/internal/` | usecase 実処理、projection、agent adapter、唯一の domain 接点 |

`interface/api` は domain / usecase を直接 import しません。
usecase との接続は `interface/application` から `usecase.jobs` top-level 公開面への import に閉じます。
`usecase.jobs` は domain を import せず、domain 接続は `usecase.internal` に閉じます。
`usecase.internal` は interface / wire schema に依存しません。
HTTP DTO、Problem Details schema、error code metadata は `contracts` に置きます。
FastAPI の exception handler と Problem Details response 生成は `interface/shared/http.py` に置きます。
表示名、response 整形は interface 側に置きます。

## 検証

```bash
uv run --extra api alembic upgrade head
uv run --extra api pytest tests/integration/api
```
