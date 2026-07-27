# AGENTS.md

このrepositoryで作業するAI coding agentの共通規則です。下位directoryに
`AGENTS.md`がある場合は、その範囲で下位規則を優先します。

## システム

Werewolf AgentはLLM agentを人狼ゲームのplayerとして動かすPython backendです。
決定的なdomain coreが完全状態を管理し、利用者には公開状態、public timeline、
認証したplayer本人のobservationだけを返します。

## 最初に読む文書

- 利用と検証: `README.md`
- 要件: `docs/design/requirements.md`
- 構造: `docs/design/architecture.md`
- 開発: `docs/design/development.md`
- 検証: `docs/design/verification.md`
- 断片的な記録: `docs/notes/`

## 絶対境界

- `Game`だけがゲーム状態を変更する。
- domainは標準libraryとdomain内部だけに依存し、Pydantic、I/O、環境変数、logging、
  database、LLMを参照しない。
- applicationのcommand、query、resultとHTTPのwire schemaを共有しない。
- game参照、player操作、observation、非同期command受付の認可はapplicationで完結する。
- applicationとagentsは相互に依存しない。
- API routeはapplicationの公開contractだけを呼ぶ。
- workerがapplication、agent、外部adapterを組み立てる。
- CLIとStreamlitはHTTP APIだけでゲームを操作する。
- public state、timeline、LLM observationへ秘匿情報を含めない。
- 外部LLM出力はschema検証後にactionへ変換する。
- 正規faction IDとwinner IDは`village`、`werewolf`、`fox`とする。

構造規則の正本は`scripts/architecture/rules.toml`です。構造テスト、分析JSON、
評価文書、図は同じ定義を使用します。

## 作業

1. 対象のdesign文書、実装、テスト、設定を確認する。
2. 原因を責務と依存境界まで絞り、同じ原因を持つ箇所を検索する。
3. 境界変更はdesign文書と構造規則へ反映する。
4. 再現テストを追加し、最小の所有moduleへ実装する。
5. 不要な旧path、fallback、重複を削除する。
6. formatter、lint、型、対象テスト、品質profileを実行する。

UI変更では自動Browser E2Eの成功後にBrowser画面確認スキルを使い、desktopとmobileの
主要状態を操作して成果物と照合します。スキルを利用できない場合はAI画面レビューだけを
`blocked`とし、自動E2Eの結果と混同しません。

後方互換は要求された場合だけ維持します。可変値は設定または定義resourceへ置き、
安定した識別子だけを所有module内で定数化します。

## コマンド

```powershell
uv run --no-project python -m scripts.environment ensure check
uv run --no-sync python -m scripts.quality auto
uv run --no-sync ruff format --check .
uv run --no-sync ruff check --no-cache .
uv run --no-sync mypy --no-incremental src
uv run --no-sync pytest
uv run --no-sync python -m scripts.quality focus
uv run --no-sync python -m scripts.quality check
uv run --no-sync python -m scripts.docs build
uv run --no-sync python -m scripts.architecture
```

品質判定はfake、fixture、localhost、Compose内serviceで完結させます。package registry、
browser配布元、image registryへの接続はenvironment準備で許可します。有料providerや
任意の外部APIを品質判定へ使用しません。

## 文書

完成した仕様は`docs/design`、調査、比較、QA、引継ぎは`docs/notes`に置きます。
説明は現在形の日本語を基本にし、コード識別子と外部API名は英語のまま扱います。

## Commit

日本語のConventional Commitsに近い一行を使います。
