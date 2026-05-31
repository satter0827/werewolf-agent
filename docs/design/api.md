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
| `GET` | `/api/v1/ruleset` | player count、roles、default role counts、default local rules |
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
| `CreateGameRequest` | game run 作成 request |
| `GameRunResponse` | 1 game run の現在 public state |
| `AdvanceGameRunResponse` | 進行後の public state と追加 timeline |
| `AdvanceUntilInputResponse` | manual input / 完了 / 上限まで進めた結果 |
| `GameTimelineResponse` | `GameTimelineItem` の page |
| `GameTimelineItem` | API / CLI / replay / SSE / UI 共通の公開履歴 |
| `PlayerObservationResponse` | manual player の private observation |
| `PlayerActionRequest` / `PlayerActionResponse` | manual action 入出力 |
| `RulesetResponse` | client bootstrapping 用の既定 ruleset metadata |

互換 alias、旧 DTO 名、旧 endpoint fallback は持ちません。

## Create Game

game 作成時の人数は `role_counts` の合計から導出します。全体人数を直接指定する field は持ちません。

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
  "human_player_id": "player-1"
}
```

local rule override 付き:

```json
{
  "seed": 42,
  "role_counts": {"werewolf": 1, "seer": 1, "knight": 1, "villager": 2},
  "human_player_id": "player-1",
  "rules": {
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

- `role_counts`: 必須。role id ごとの人数。合計が configured min / max の範囲内で、人狼側 1 以上、村側 1 以上
- `human_player_id`: 任意。`role_counts` の合計から生成される `player-1` から `player-N` のいずれか。指定時だけ作成レスポンスに `control_tokens` を返す
- `rules`: 任意。game run ごとの local rule override。省略時は `interface/application` が runtime で読み込んだ default local rules を使う

role の faction / ability、LLM agent の名前や性格は request body では受け取りません。これらは definition resource として読み込みます。agent は現在 `interface/application` が `llm` と `human_player_id` から内部設定を生成します。

| 定義体 | 既定 | override |
| --- | --- | --- |
| game rules | `backend/src/werewolf_agent/resources/game/rules.toml` | `WEREWOLF_GAME_RULES_FILE` |
| game roles | `backend/src/werewolf_agent/resources/game/roles.toml` | `WEREWOLF_GAME_ROLES_FILE` |
| LLM players | `backend/src/werewolf_agent/resources/llm/players.toml` | `WEREWOLF_LLM_PLAYERS_FILE` |
| LLM prompt | `backend/src/werewolf_agent/resources/prompts/agent_decision.toml` | `WEREWOLF_LLM_PROMPT_FILE` |
| LLM fake responses | `backend/src/werewolf_agent/resources/llm/fake_responses.toml` | `WEREWOLF_LLM_FAKE_RESPONSES_FILE` |

定義体 path と定義体値の読み込みは `interface/runtime` の共通 loader に集約します。定義体は `AppSettings` 構築時に読み込み・検証し、role 定義体の `default_role_counts` は configured player count 範囲をすべて持つ必要があります。`domain` と `usecase` は source path と省略時 default を知らず、`interface/application` から値として注入されたものだけを使います。`GET /ruleset` は client 起動用に `roles`、`default_role_counts`、`default_rules` を返します。

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
- night action actor / action type
- guard target
- inspection result
- private observation
- `private_state`
- token、API key、authorization
- raw prompt / raw provider response

公開 timeline に出すもの:

- public speech message
- vote actor / target
- vote result
- night killed player id の有無

## Reveal API

観戦 UI 用に、通常の public API とは別の専用公開面を持ちます。

- route: `GET /api/v1/games/{game_id}/reveal`
- enable flag: `WEREWOLF_REVEAL_API_ENABLED`
- default: `true`
- disabled 時: `403 auth.forbidden` の Problem Details

`reveal` は開発・デモ用の観戦画面だけが読む DTO です。public state、public timeline、private observation の契約は変えません。

返すもの:

- `role_counts`、local `rules`、`seed`
- 全 player の role / faction / alive / status
- pending vote / pending night action
- 解決済み vote / night record
- winner、day、phase、version

返さないもの:

- control token
- prompt、API key、raw provider response
- repository の `private_state` そのもの

Streamlit の Play は従来通り private observation だけを読み、全役職や夜行動 target を表示しません。Streamlit の Observe は `human_player_id=None` で game を作成し、操作 UI を出さずに reveal DTO から全情報を表示します。

## Manual Player

`human_player_id` を含む game 作成レスポンスは、作成時だけ `control_tokens` を返します。API は token hash だけを保存し、平文 token は保存しません。

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
| `interface/runtime/` | settings、definition TOML loader、logging bootstrap、structlog context |
| `interface/shared/http.py` | FastAPI Problem Details 変換 |
| `interface/api/routers.py` | endpoint |
| `interface/application/games.py` | transaction、依存注入、wire schema 変換 |
| `interface/application/repositories.py` | SQLAlchemy repository adapter |
| `interface/application/models.py` | `game_runs` / `game_events` / public read model ORM |
| `usecase/jobs/` | `GameUseCases` facade、command、repository / telemetry port |
| `usecase/internal/` | usecase 実処理、projection、agent adapter、唯一の domain 接点 |

境界:

- `interface/api` は domain / usecase を直接 import しない
- usecase との接続は `interface/application` から `werewolf_agent.usecase.jobs` top-level 公開面への import に閉じる。top-level 公開面は facade、command、query、repository / telemetry port、application bridge が必要とする永続化 contract に絞る
- `usecase/jobs` は domain を import せず、domain 接続は `usecase/internal` に閉じる
- `usecase/internal` は interface / wire schema に依存しない
- HTTP DTO、Problem Details schema、error code metadata は `contracts` に置く

## 検証

```bash
uv run --extra api alembic upgrade head
uv run --extra api pytest tests/integration/api
```
