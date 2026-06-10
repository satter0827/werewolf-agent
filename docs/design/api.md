# API

この文書は、CLI / Streamlit / worker が共有する外部契約を固定します。
判断履歴や作業メモは `docs/notes/` に置きます。

## 目的

- LLM 同士の game と 1 人 manual player 混在 game を、`GameApi` port と Supabase queue worker で決着まで進める
- React / CLI / Streamlit は Supabase Auth / Data API を正本にし、未ログイン時も anonymous sign-in で authenticated session を作る
- public response、public timeline、operational log に role、night action target、private state、token、API key、raw provider response を出さない
- 旧 endpoint、旧 field、旧 DTO 名、旧 save format の fallback は持たない

## 現在地

- Supabase Auth / Data API direct access
- Supabase queue worker
- `llm` agent と LangChain provider による自動進行
- 1 game につき 1 人の manual player
- admin reveal DTO による observer 表示
- RFC 9457 Problem Details 互換の error payload
- React UI
- 複数 manual player は未実装

## 実行モデル

backend game HTTP API は提供しません。React / CLI / Streamlit は Supabase queue と Data API だけを使います。

| mode | 動作 |
| --- | --- |
| 匿名 session | `signInAnonymously()` / `ensure_session()` で authenticated session を作り、`game_operation_requests` に操作を enqueue する |
| worker | queued operation を claim し、Python usecase と configured LLM provider を実行する |

Supabase mode では worker が `games`、`game_summaries`、`game_public_turns`、`game_player_observations`、`llm_invocations` を更新します。operation request は完了時に `result_payload`、失敗時に Problem Details 互換の `error_payload` を持ちます。LLM provider 呼び出しは UI / CLI process の外、worker transaction の中で trace とともに保存します。

## Wire Schemas

ここにある schema は `GameApi` port と Supabase operation request で共有する外部契約です。

| Schema | 用途 |
| --- | --- |
| `GameSetupOptionsResponse` | client bootstrapping 用の role、scenario、preset、character、default rules |
| `CreateGameRequest` | game 作成 request |
| `GameResponse` | 1 game の public state |
| `GameListResponse` | `PublicGameSummary` の page |
| `AdvanceGameResponse` | 進行後の public state と追加 public timeline |
| `AdvanceGameJobResponse` | advance job の状態、poll URL、完了時 result、失敗時 Problem Details |
| `GameTimelineResponse` | `GameTimelineItem` の page |
| `PlayerObservationResponse` | authenticated manual player の private observation |
| `PlayerActionRequest` / `PlayerActionResponse` | manual action 入出力 |
| `GameRevealResponse` | admin observer 用の専用 reveal DTO |

## Create Game

`GameApi.create_game` は `game_operation_requests` へ `operation_type = create_game` を enqueue します。

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

AI strategy 指定付き:

```json
{
  "seed": 42,
  "role_counts": {"werewolf": 1, "seer": 1, "knight": 1, "villager": 3},
  "agent_strategy_id": "stable_fast"
}
```

制約:

- `role_counts`: 必須。合計が configured min / max の範囲内で、人狼側 1 以上、村側 1 以上
- `manual_player_id`: 任意。生成される `player-1` から `player-N` のいずれか。操作権限は response credential ではなく Supabase participant record で決まる
- `rules`: 任意。省略時は `api.usecase_bridge` が runtime default を注入する
- `narration_mode`: 任意。省略時は `WEREWOLF_GAME_DEFAULT_NARRATION_MODE` の値を注入する
- `agent_strategy_id`: 任意。省略時は `WEREWOLF_LLM_DEFAULT_AGENT_STRATEGY_ID` の値を注入し、game config に保存する
- `character_assignments`、`custom_roles`、`custom_characters`: Streamlit session 内の追加定義を game 作成 request に同梱するための field

## Setup Options

`GameApi.get_setup_options` と React client は、client の開始画面を作るための metadata だけを返します。公開済みの `definition_items(scope = 'system', kind = 'setup_options', item_key = 'default')` を読み、React / CLI / Streamlit の bootstrapping を同じ Supabase Data API 契約に揃えます。

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
- `agent_strategies`
- `default_agent_strategy_id`

worker / migration で publish する元データは runtime definition から作る `api.setup_options` の projection と同じ wire schema に揃えます。definition path と TOML 読み込みは `commons.resources` に集約します。domain と usecase は source path、packaged default、`.env` を知りません。

## Pagination

`GameApi.list_games` と `GameApi.get_timeline` の `limit` は省略できます。省略時の件数と最大値は runtime settings で管理します。

- game list: `WEREWOLF_API_GAME_LIST_DEFAULT_LIMIT` / `WEREWOLF_API_GAME_LIST_MAX_LIMIT`
- timeline: `WEREWOLF_API_TIMELINE_DEFAULT_LIMIT` / `WEREWOLF_API_TIMELINE_MAX_LIMIT`

最大値を超える `limit` は `400 config.invalid_value` を返します。

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

## Reveal

`GameApi.get_game_reveal` は admin observer 用の専用 DTO を返します。Supabase の `game_reveals` table と RLS / admin claim が公開範囲を決めます。`WEREWOLF_REVEAL_API_ENABLED=false` の場合、worker は既存 reveal payload を削除します。

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

manual player は `GameApi.create_game` の `manual_player_id` で 1 人だけ指定できます。Supabase worker は `game_participants` に `auth.uid()` と player id を保存し、以後の private observation / manual action は RLS と participant record で制御します。React / CLI / Streamlit は seat credential を扱いません。

| 状態 | Status | Code |
| --- | --- | --- |
| Supabase session なし | `401` | `auth.required` |
| participant record がない player 操作 | `403` | `auth.forbidden` |

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

provider は選択済み `agent_strategy_id` の LangGraph `StateGraph` を実行し、Pydantic で `AgentDecision` を検証します。不正 JSON、不正 action、不正 target、長すぎる speech、repair 失敗、provider 呼び出し失敗は game を止めず deterministic fallback に落とします。raw prompt、raw response、API key は public response、public timeline、operational log へ出しません。

strategy 詳細は [Agent Strategies](agent-strategies.md) を参照してください。

## Errors

Error payload は RFC 9457 Problem Details 互換です。Supabase worker は `game_operation_requests.error_payload` に保存します。

| Status | Code | 例 |
| --- | --- | --- |
| `400` | `request.validation_failed` | body / query validation |
| `401` | `auth.required` | Supabase session がない |
| `403` | `auth.forbidden` | RLS で許可されない user / game / player |
| `404` | `resource.not_found` | game が存在しない |
| `409` | `game.invalid_phase` | manual input 待ち、または終了済み game の進行。advance では job.error に格納する |
| `422` | `game.invalid_action` | action ルール違反 |
| `500` | `internal.unexpected` | 想定外エラー |

## 実装位置

| Path | 責務 |
| --- | --- |
| `contracts/schemas.py` | GameApi / Supabase で共有する wire DTO、Problem Details schema |
| `contracts/errors.py` | error code metadata |
| `api/ports.py` | CLI / Streamlit が使う `GameApi` port |
| `api/factory.py` | SupabaseGameApi の構築と匿名 session 確保 |
| `api/usecase_bridge.py` | settings、definition、LLM provider を usecase 用に組み立てる |
| `api/setup_options.py` | runtime definition から開始画面 metadata を作る projection |
| `api/supabase/` | Supabase Auth / Data API adapter |
| `api/supabase/worker/` | operation request worker、Postgres repository adapter、LLM trace sink |
| `entrypoint/requests.py` | CLI / Streamlit 共通 request builder |
| `usecase/jobs/` | `GameService` facade、command / query、repository / telemetry port |
| `usecase/internal/` | workflow、projection、agent adapter、唯一の domain 接点 |

## 検証

```bash
uv run pytest tests/unit/api tests/unit/entrypoint tests/unit/commons
uv run pytest tests/unit/architecture/test_architecture_boundaries.py
supabase migration up
uv run --extra worker werewolf-agent-worker run
```
