# API

この文書は、Sphinx で公開する完成版の API 契約です。
作業途中の判断、handoff、未確定メモは `docs/notes/` に置きます。

FastAPI は CLI / Streamlit / 将来 UI が使う最小の公開面です。DB には完全状態を保存しますが、HTTP response と SSE には public state、public timeline、Problem Details だけを出します。

## 現在の範囲

- 同期 REST API
- public timeline SSE
- `llm` agent と LangChain `fake` provider による自動進行
- game 作成、一覧、状態取得、進行、timeline 取得
- 1 game につき 1 人の manual player 用 private observation / action
- RFC 9457 互換 Problem Details
- React UI、複数 human player、永続 login/session は未実装

## Endpoints

| Method | Path | 用途 |
| --- | --- | --- |
| `GET` | `/api/v1/health` | `{"status":"ok","service":"werewolf-agent-api"}` |
| `GET` | `/api/v1/ruleset` | player count、roles、phases、agent types |
| `POST` | `/api/v1/games` | game run 作成 |
| `GET` | `/api/v1/games?status=<status>&limit=<n>&offset=<n>` | public run summary 一覧 |
| `GET` | `/api/v1/games/{game_id}` | public state 取得 |
| `POST` | `/api/v1/games/{game_id}/advance` | 現在の usecase step を 1 回進める |
| `POST` | `/api/v1/games/{game_id}/advance-until-input?max_steps=<n>` | manual input、完了、上限まで自動進行 |
| `GET` | `/api/v1/games/{game_id}/timeline?after=<seq>&limit=<n>` | public timeline を sequence 昇順で取得 |
| `GET` | `/api/v1/games/{game_id}/timeline/stream?after=<seq>&limit=<n>` | public timeline を SSE 形式で取得 |
| `GET` | `/api/v1/games/{game_id}/players/{player_id}/observation` | token 付き private observation |
| `POST` | `/api/v1/games/{game_id}/players/{player_id}/actions` | token 付き manual action |

## Wire Schemas

主要 DTO 名は外部契約として次に固定します。

| Schema | 用途 |
| --- | --- |
| `CreateGameRunRequest` | game run 作成 request |
| `GameRunResponse` | 1 game run の現在 public state |
| `AdvanceGameRunResponse` | 進行後の public state と追加 timeline |
| `AdvanceUntilInputResponse` | manual input / 完了 / 上限まで進めた結果 |
| `GameTimelineResponse` | `GameTimelineItem` の page |
| `GameTimelineItem` | API / CLI / replay / SSE / UI 共通の公開履歴 |
| `PlayerObservationResponse` | manual player の private observation |
| `PlayerActionRequest` / `PlayerActionResponse` | manual action 入出力 |

互換 alias、旧 DTO 名、旧 endpoint fallback は持ちません。

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
    "allow_self_vote": false,
    "allow_action_revisions": false
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

- `player_count`: 既定では 5〜8。省略時の解決は interface / usecase の設定値で行う
- `players`: 指定時は player count と件数を一致させる。`id` は normalize 後に一意
- `agent.type`: 現在は `llm` のみ。provider は `WEREWOLF_LLM_PROVIDER=fake`
- `players[].agent_type`: `llm` または `human`。`human` は 1 game につき 1 人まで
- `role_counts`: 合計が player count と一致し、人狼 1 以上、村側 1 以上
- `tie_break_policy`: `no_elimination` または `random_elimination`
- `day_speech_turns`: 1〜5
- `allow_self_vote`: `false` の場合、自分への投票を拒否する
- `allow_action_revisions`: 既定 `false`。同じ phase / day の発言、投票、夜行動の再提出を拒否する

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

## Timeline

外部公開の履歴は `GameTimelineItem` だけです。永続化内部では event stream と turn read model を保持してよいですが、API、CLI、SSE、replay、UI は同じ schema を使います。

`GameTimelineItem`:

- `sequence`: public timeline sequence
- `event_sequence`: 元 event stream sequence
- `version`: 対応する public state version
- `phase`、`day`
- `actor_id`: public に出してよい actor id。private target は出さない
- `event_type`
- `payload`: public-safe payload
- `occurred_at`

Cursor:

- request: `after=<last_sequence>&limit=<n>`
- response: `next_after`

SSE:

- event: `timeline_item`
- id: `sequence`
- data: `GameTimelineItem` JSON

公開 timeline に出さないもの:

- role assignment
- night action target
- private observation
- `private_state`
- token、API key、authorization
- raw prompt / raw provider response

## Manual Player

`players[].agent_type=human` を含む game 作成レスポンスは、作成時だけ `control_tokens` を返します。API は token hash だけを保存し、平文 token は保存しません。

private observation と manual action は `Authorization: Bearer <token>` が必要です。

| 状態 | Status | Code |
| --- | --- | --- |
| token なし | `401` | `auth.required` |
| 不正 token / 非 human player | `403` | `auth.forbidden` |

manual action body:

```json
{"type": "speech", "message": "I am checking the table."}
```

`type` は `speech`、`vote`、`werewolf_attack`、`seer_inspect`、`knight_guard`、`pass` です。target が必要な action は `target_id` を指定します。

`available_actions` は「今その player が送信できる action」だけを返します。発言済み、投票済み、夜行動済みの場合は既定で空になります。再送された action は保存せず、`422 game.invalid_action` を返します。

`POST /games/{game_id}/advance` は manual player の入力待ちが残っている場合、phase を進めず `409 game.invalid_phase` を返します。UI は `advance-until-input` を使い、LLM action と phase 進行をまとめて進め、`stop_reason` が `manual_input_required`、`completed`、`hit_limit` のいずれかになるまで待ちます。

## Run Summary

`GET /games` は CLI `runs` と UI 一覧用の public summary だけを返します。

返すもの:

- status、phase、day、version、seed
- player_count、alive_count、winner
- step_count、turn_count
- created_at、updated_at、completed_at

返さないもの:

- role assignment
- private state
- manual player token

## Errors

Error response は RFC 9457 Problem Details 互換です。
`Content-Type` は `application/problem+json`。
API response には `X-Trace-Id` header を付け、Problem Details の `trace_id` と対応させます。

| Status | Code | 例 |
| --- | --- | --- |
| `400` | `request.validation_failed` | body / query validation |
| `401` | `auth.required` | Bearer token がない |
| `403` | `auth.forbidden` | token 不正、または非 manual player |
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
| `interface/runtime/` | settings、logging bootstrap、structlog context |
| `interface/shared/http.py` | FastAPI Problem Details 変換 |
| `interface/api/routers.py` | endpoint |
| `interface/application/games.py` | transaction、依存注入、wire schema 変換 |
| `interface/application/repositories.py` | SQLAlchemy repository adapter |
| `interface/application/models.py` | `game_runs` / `game_events` / public read model ORM |
| `usecase/jobs/` | `GameUseCases` facade、DTO、repository / telemetry port |
| `usecase/internal/` | usecase 実処理、projection、agent adapter、唯一の domain 接点 |

境界:

- `interface/api` は domain / usecase を直接 import しない
- usecase との接続は `interface/application` から `werewolf_agent.usecase.jobs` top-level 公開面への import に閉じる
- `usecase/jobs` は domain を import せず、domain 接続は `usecase/internal` に閉じる
- `usecase/internal` は interface / wire schema に依存しない
- HTTP DTO、Problem Details schema、error code metadata は `contracts` に置く

## 検証

```bash
uv run --extra api alembic upgrade head
uv run --extra api pytest tests/integration/api
```
