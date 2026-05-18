# API 設計メモ

## 目的

Django API の MVP は、CLI、将来の Streamlit / React 観戦 UI、外部クライアントから使える公開ゲーム状態を提供することを目的にします。
ゲーム進行は `domain.Game` と `FakeLlmAgent` を使い、API service が永続化と公開 DTO への変換を担当します。

## 現在の状態

- `GET /api/health/` は死活監視用です。
- `GET /api/rulesets/default/` は MVP のプレイヤー数、役職、フェーズ、agent type を返します。
- `POST /api/games/` は dummy agent だけを受け付け、ゲーム run を作成します。
- `GET /api/games/{game_id}/` は公開状態だけを返します。
- `POST /api/games/{game_id}/steps/` は現在フェーズの dummy action を生成し、1 ステップ進めます。
- `POST /api/games/{game_id}/advance/` は `steps` と同じ互換エイリアスです。
- `GET /api/games/{game_id}/events/?after={sequence}` は public event だけを sequence 昇順で返します。

## 公開情報と秘匿情報

公開 API には、プレイヤー名、生死状態、現在フェーズ、日数、勝敗、public event だけを含めます。
役職割り当て、夜行動、LLM 入力、debug state は API レスポンスに含めません。

内部保存では `GameRun.private_state` に domain snapshot を持ちます。
これは deterministic engine の再開用であり、公開 API や公開ログへ出しません。

## 作成リクエスト例

```json
{
  "seed": 42,
  "players": [
    {"id": "p1", "name": "Alice", "agent_type": "dummy"},
    {"id": "p2", "name": "Bob", "agent_type": "dummy"},
    {"id": "p3", "name": "Carol", "agent_type": "dummy"},
    {"id": "p4", "name": "Dave", "agent_type": "dummy"},
    {"id": "p5", "name": "Eve", "agent_type": "dummy"}
  ]
}
```

簡易作成では `player_count` だけも指定できます。

```json
{"player_count": 6, "seed": 1}
```

## エラー

API エラーは RFC 9457 Problem Details (`application/problem+json`) で返します。

- 不正な request body: `400 request.validation_failed`
- 存在しない game: `404 not_found`
- 終了済みゲームの進行: `409 game.invalid_phase`
- 不正な player count / agent type: `422 game.invalid_action`

## 実行コマンド

```bash
uv run --extra api python backend/manage.py check
uv run --extra api pytest tests/test_api_health.py tests/test_api_errors.py tests/test_api_games.py
uv run --extra api python backend/manage.py runserver
```

ローカル確認:

```text
http://127.0.0.1:8000/api/rulesets/default/
```

## 未決事項

- 認証と player private observation
- 人間プレイヤーの発話、投票、夜行動 API
- LLM provider 呼び出しと background job 化
- SSE / WebSocket によるイベント配信
