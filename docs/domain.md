# Domain 実装メモ

## 目的

- `werewolf_agent.domain.models` を deterministic core の唯一の公開境界にする
- CLI / API / agents は `domain.models` だけを import し、内部ルール処理へ直接依存しない
- domain は headless に保ち、設定値、乱数、ログ出力先を外部から注入できるようにする

## 現在の状態

- `Game.start(...)` が新規ゲーム開始の入口
- `Game` は薄い facade として、投票、夜行動、観測生成、フェーズ遷移を内部モジュールへ委譲する
- 公開型は `models.py` に集約し、役職、フェーズ、状態、観測、構造化 action、解決結果を Pydantic model と enum で表す
- Fake LLM は `werewolf_agent.agents.FakeLlmAgent` として実装し、`Observation` から構造化 action を返す

## 境界ルール

- 外部層は `from werewolf_agent.domain.models import ...` または `from werewolf_agent.domain import ...` を使う
- `_rules.py`、`_voting.py`、`_night_actions.py`、`_observations.py`、`_transitions.py` は private 実装として扱う
- domain 内では `.env`、`get_settings()`、標準 logging、JSONL 書き込みを直接扱わない
- domain event は `DomainEventSink` に渡すだけにし、永続化や redaction は外側の層で扱う

## 実行コマンド

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy backend/src
```

## 次の一手

- API `games` service は `Game` と `FakeLlmAgent` を組み合わせ、公開 DTO と public event stream に変換する
- 次は人間プレイヤーや LLM provider が action を投入できる application 層の adapter を追加する
- Streamlit / React は `GameSnapshot` と `Observation` を直接公開せず、API DTO を通して扱う
