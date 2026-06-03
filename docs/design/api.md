# API

この文書は、FastAPI / CLI / Streamlit が共有する外部契約を固定します。
判断履歴や作業メモは `docs/notes/` に置きます。

## 目的

- LLM 同士の game と 1 人 manual player 混在 game を、公開 API だけで決着まで進める
- public response、public timeline、operational log に role、night action target、private state、token、API key、raw provider response を出さない
- 旧 endpoint、旧 field、旧 DTO 名、旧 save format の fallback は持たない

## 現在地

- 同期 REST API
- `llm` agent と LangChain provider による自動進行
- 1 game につき 1 人の manual player
- dedicated reveal API による observer / demo 表示
- RFC 9457 Problem Details
- React UI、複数 manual player、永続 login / session は未実装

## Endpoints

| Method | Path | 用途 |
| --- | --- | --- |
| `GET` | `/api/v1/health` | health check |
| `GET` | `/api/v1/setup-options` | game 作成用 metadata |
| `POST` | `/api/v1/games` | game 作成 |
| `GET` | `/api/v1/games?status=<status>&limit=<n>&offset=<n>` | public game summary 一覧 |
| `GET` | `/api/v1/games/{game_id}` | public state |
| `POST` | `/api/v1/games/{game_id}/advance` | 現在の usecase step を 1 回進める |
| `GET` | `/api/v1/games/{game_id}/timeline?after=<seq>&limit=<n>` | public timeline |
| `GET` | `/api/v1/games/{game_id}/reveal` | observer / demo 用 reveal DTO |
| `GET` | `/api/v1/games/{game_id}/players/{player_id}/observation` | Bearer token 付き private observation |
| `POST` | `/api/v1/games/{game_id}/players/{player_id}/actions` | Bearer token 付き manual action |

`advance` は常に 1 step だけ進めます。manual input が必要な場合は state を変更せず `409 game.invalid_phase` を返します。CLI と Streamlit は `advance` を繰り返し呼び、入力待ち、完了、上限到達、停止操作のいずれかで止めます。

## Wire Schemas

| Schema | 用途 |
| --- | --- |
| `GameSetupOptionsResponse` | client bootstrapping 用の role、scenario、preset、character、default rules |
| `CreateGameRequest` | game 作成 request |
| `GameResponse` | 1 game の public state。作成時だけ `manual_player` を含める |
| `ManualPlayerCredential` | `player_id` と token。作成レスポンスで 1 回だけ返す |
| `GameListResponse` | `PublicGameSummary` の page |
| `AdvanceGameResponse` | 進行後の public state と追加 public timeline |
| `GameTimelineResponse` | `GameTimelineItem` の page |
| `PlayerObservationResponse` | authenticated manual player の private observation |
| `PlayerActionRequest` / `PlayerActionResponse` | manual action 入出力 |
| `GameRevealResponse` | observer / demo 用の専用 reveal DTO |

## Create Game

人数は `role_counts` の合計から導出します。全体人数だけを指定する field は持ちません。

最小:

```json
{
  "seed": 42,
  "role_counts": {"werewolf": 1, "seer": 1, "knight": 1, "villager": 2}
}
```

manual player 付き:

```json
{
  "seed": 42,
  "role_counts": {"werewolf": 1, "seer": 1, "knight": 1, "villager": 3},
  "manual_player_id": "player-1"
}
```

local rule override 付き:

```json
{
  "seed": 42,
  "role_counts": {"werewolf": 1, "seer": 1, "knight": 1, "villager": 2},
  "rules": {
    "day_speech_limit_per_player": 1,
    "allow_self_vote": false,
    "allow_vote_revision": false,
    "allow_night_action_revision": false,
    "enable_first_night_attack": true,
    "enable_no_elimination_on_tie": true,
    "enable_random_elimination_on_tie": false,
    "allow_knight_self_guard": true,
    "allow_knight_repeat_guard": true,
    "allow_seer_self_inspect": false,
    "allow_werewolf_friendly_fire": false,
    "reveal_role_on_death": false
  }
}
```

制約:

- `role_counts`: 必須。合計が configured min / max の範囲内で、人狼側 1 以上、村側 1 以上
- `manual_player_id`: 任意。生成される `player-1` から `player-N` のいずれか
- `manual_player`: `POST /games` の response でだけ返す。`GET /games/{game_id}` には含めない
- `rules`: 任意。省略時は `interface/application` が runtime default を注入する
- `character_assignments`、`custom_roles`、`custom_characters`: Streamlit session 内の追加定義を game 作成 request に同梱するための field

## Setup Options

`GET /setup-options` は client の開始画面を作るための metadata だけを返します。

- `player_count`
- `roles`
- `abilities`
- `scenarios`
- `setup_presets`
- `characters`
- `default_role_counts`
- `default_rules`
- `default_scenario_id`
- `default_setup_preset_id`
- `default_narration_mode`

definition path と TOML 読み込みは `interface/runtime` に集約します。domain と usecase は source path、packaged default、`.env` を知りません。

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
- token
- prompt、API key、raw provider response

## Timeline

`GameTimelineItem` は外部公開履歴の唯一の schema です。

- `sequence`: public timeline sequence
- `event_sequence`: 元 event stream sequence
- `version`: 対応する public state version
- `phase`、`day`
- `actor_id`: public に出してよい actor id
- `event_type`
- `narration`
- `payload`: public-safe payload
- `occurred_at`

Cursor:

- request: `after=<last_sequence>&limit=<n>`
- response: `next_after`

公開 timeline に出さないもの:

- role assignment
- night action target
- guard target
- inspection result
- private observation
- `private_state`
- token、API key、authorization
- raw prompt / raw provider response

## Reveal API

`GET /api/v1/games/{game_id}/reveal` は observer / demo 用の専用 DTO です。
`WEREWOLF_REVEAL_API_ENABLED=false` の場合は `403 auth.forbidden` を返します。

返すもの:

- `role_counts`、local `rules`、`seed`
- 全 player の role / faction / alive / status
- pending vote / pending night action
- 解決済み vote / night record
- winner、day、phase、version

返さないもの:

- token
- prompt、API key、raw provider response
- repository の `private_state` そのもの

## Manual Player

manual player は `POST /games` の `manual_player_id` で 1 人だけ指定できます。
作成 response の `manual_player` は次の形です。

```json
{
  "player_id": "player-1",
  "token": "<one-time-visible-token>"
}
```

private observation と manual action は `Authorization: Bearer <token>` を使います。

| 状態 | Status | Code |
| --- | --- | --- |
| token なし | `401` | `auth.required` |
| token 不正、または対象 player が manual player ではない | `403` | `auth.forbidden` |

manual action:

```json
{"type": "speech", "message": "I am checking the table."}
```

target が必要な action は `target_id` を指定します。`available_actions` はその player が今送信できる action だけを返します。発言済み、投票済み、夜行動済みの場合は空になります。

## LLM Decision

LLM provider には `AgentObservation` だけを渡します。

- `available_actions`: 送信可能な action
- `legal_targets`: action ごとの合法 target id
- `speeches` / `vote_rounds`: public history
- `known_roles`: その player が観測できる role だけ

provider は Pydantic で `AgentDecision` を検証します。不正 JSON、不正 action、不正 target は保存せず `pass` fallback にします。raw prompt、raw response、API key は保存・公開・ログ出力しません。

## Errors

Error response は RFC 9457 Problem Details 互換です。
`Content-Type` は `application/problem+json` です。

| Status | Code | 例 |
| --- | --- | --- |
| `400` | `request.validation_failed` | body / query validation |
| `401` | `auth.required` | Bearer token がない |
| `403` | `auth.forbidden` | token 不正、または非 manual player |
| `404` | `resource.not_found` | game が存在しない |
| `405` | `request.method_not_allowed` | method が未対応 |
| `409` | `game.invalid_phase` | manual input 待ち、または終了済み game の進行 |
| `422` | `game.invalid_action` | action ルール違反 |
| `500` | `internal.unexpected` | 想定外エラー |

## 実装位置

| Path | 責務 |
| --- | --- |
| `contracts/schemas.py` | HTTP wire DTO、Problem Details schema |
| `contracts/errors.py` | error code metadata |
| `interface/runtime/` | settings、definition loader、logging bootstrap |
| `interface/api/routers.py` | endpoint |
| `interface/application/games.py` | transaction、依存注入、wire schema 変換 |
| `interface/application/repositories.py` | SQLAlchemy repository adapter |
| `usecase/jobs/` | `GameService` facade、command / query、repository / telemetry port |
| `usecase/internal/` | workflow、projection、agent adapter、唯一の domain 接点 |

## 検証

```bash
uv run --extra api alembic upgrade head
uv run --extra api pytest tests/integration/api
```
