# Agent Strategies

この文書は、LLM agent の意思決定 strategy と LangGraph 実行 graph の運用定義を固定します。
UI には graph 内部ではなく `AI strategy` として表示します。

## 目的

- LLM の出力ゆらぎ、parse 失敗、不正 target、provider 呼び出し失敗で game を止めない
- game ごとに選んだ `agent_strategy_id` を保存し、demo と worker の advance で同じ strategy を使う
- graph 定義を TOML と設定値で切り替え、任意 import path や任意 Python 実行を許可しない
- public response、public timeline、Streamlit UI に raw prompt、raw response、graph state、secret、private night action を出さない

## 現在地

初期 strategy は 3 つです。既定は `stable_fast` です。

| id | 表示名 | 狙い |
| --- | --- | --- |
| `stable_fast` | Stable Fast | 1 回の LLM 呼び出し、検証、1 回 repair、deterministic fallback で速く止まらない |
| `role_basic` | Role Basic | role ごとの短い tactical hint を加え、安定性を維持しながら基本戦術を分ける |
| `target_ranker` | Target Ranker | target-taking action の合法 target を deterministic に順位化し、投票、襲撃、占い、護衛の品質を上げる |

`discussion_tactics` は初期採用しません。昼発言を疑い、弁明、誘導、同調に分ける候補ですが、token と latency が増えるため後続 preset として扱います。

## 設定

運用値の正本は `backend/src/werewolf_agent/resources/settings/defaults.toml` です。

| 設定 | 既定 | 用途 |
| --- | --- | --- |
| `llm_default_agent_strategy_id` | `stable_fast` | game 作成時に request が省略した場合の strategy |
| `llm_decision_graphs_file` | 空文字 | 外部 decision graph TOML への override path |
| `llm_structured_output_mode` | `auto` | structured output の使用方針 |
| `llm_validation_retry_count` | `1` | validation / repair の上限 |
| `llm_graph_max_steps` | `8` | LangGraph 実行 step 上限 |
| `llm_fallback_policy` | `deterministic_legal_action` | fallback の決定方針 |

`llm_decision_graphs_file` が空の場合は packaged default の
`backend/src/werewolf_agent/resources/llm/decision_graphs.toml` を使います。
外部 TOML を指定しても、node は登録済み node id だけを参照できます。

## Graph Definition

`decision_graphs.toml` は strategy metadata、node、edge、route を持ちます。
定義体は実行順と条件分岐だけを表します。Python import path、prompt template path、shell command、任意 code は書けません。

登録済み node:

| node id | 責務 |
| --- | --- |
| `normalize_observation` | `AgentObservation` から公開観測だけを graph state に正規化する |
| `choose_required_action` | phase と `available_actions` から action type を固定する |
| `role_hint` | role ごとの短い tactical hint を追加する |
| `rank_targets` | 合法 target だけを deterministic に順位化する |
| `build_prompt_context` | 合法 target、直近 public history、role、profile を短く prompt 化する |
| `invoke_model` | LangChain model を呼び、structured output 対応時はそれを使う |
| `validate_action` | `AgentDecision`、action type、target、message 長、phase 整合性を検証する |
| `repair_once` | 不正 JSON、不正 target、長すぎる speech を 1 回だけ補正する |
| `deterministic_fallback` | 失敗時に seed と合法 action から安全な action を返す |

登録済み endpoint は `START` と `END` だけです。
route は `validate_action` から `valid`、`invalid`、`failed` を返します。

## Runtime Flow

`stable_fast` の基本 flow:

```text
START
  -> normalize_observation
  -> choose_required_action
  -> build_prompt_context
  -> invoke_model
  -> validate_action
  -> route_validation
       valid   -> END
       invalid -> repair_once -> validate_action
       failed  -> deterministic_fallback -> END
```

`role_basic` は `choose_required_action` の後に `role_hint` を通します。
`target_ranker` は `choose_required_action` の後に `rank_targets` を通します。

## Wire And Persistence

公開 wire schema に増える field は最小限です。

- `GameSetupOptionsResponse.agent_strategies`
- `GameSetupOptionsResponse.default_agent_strategy_id`
- `CreateGameRequest.agent_strategy_id`

UI は `agent_strategies` の表示名だけを使います。node、edge、route、raw graph config は表示しません。
`CreateGameCommand` は `agent_strategy_id` を受け取り、game の persisted config に保存します。
advance 時は session state ではなく保存済み config から strategy を復元します。

## Stability

- LLM parse failure、validation failure、不正 target、長すぎる speech、repair 失敗、provider 呼び出し失敗は deterministic fallback に落とす
- 起動時、設定構築時の unsupported provider、依存不足、strategy 定義不整合は設定エラーとして扱う
- domain core へ渡すのは検証済み `Action` だけにする
- 死亡 player、終了済み game、合法 action なし、manual player 待ちは LLM 呼び出し前に usecase 側で止める
- public timeline と public response には graph state、raw prompt、raw response、secret、private night action を出さない

LLM trace には、provider 改善用の admin-only record として prompt message、prompt hash、raw response、parsed decision を保存します。
request payload には `agent_strategy_id`、`decision_graph_id`、`graph_node`、`route`、`validation_status`、`fallback_reason` を入れます。
`latency_ms` は trace record の top-level field として保存します。

## 検証

- setup options は 3 strategy と `stable_fast` default を返す
- Streamlit setup draft は `agent_strategy_id` を保持し、create request に渡す
- unknown `agent_strategy_id` は validation error にする
- fallback は同じ seed と observation で同じ合法 action を返す
- `role_basic` は role 別 hint node を通る
- `target_ranker` は合法 target だけを順位候補にする
- fake provider で seed 固定の 1 game を最後まで進める
- architecture test で resource loading と layer boundary を固定する
