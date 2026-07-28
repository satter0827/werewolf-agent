# AGENTS.md

このリポジトリで作業するAI coding agentの共通規則である。下位ディレクトリに
`AGENTS.md`がある場合は、その範囲で下位規則を優先する。

## システム

Werewolf AgentはLLMエージェントを人狼ゲームのプレイヤーとして動かすPythonバックエンドである。
決定的なdomain coreが完全状態を管理し、利用者には公開状態、public timeline、
認証したプレイヤー本人のobservationだけを返す。

## 最初に読む文書

- 利用と検証: `README.md`
- 品質・環境・レビュー操作: `scripts/README.md`
- 要件: `docs/design/requirements.md`
- 構造: `docs/design/architecture.md`
- 開発: `docs/design/development.md`
- 検証: `docs/design/verification.md`
- 断片的な記録: `docs/notes/`

## 絶対境界

- `Game`だけがゲーム状態を変更する。
- domainは標準libraryとdomain内部だけに依存し、Pydantic、I/O、環境変数、logging、
  database、LLMを参照しない。
- applicationのコマンド、query、resultとHTTPのwire schemaを共有しない。
- game参照、プレイヤー操作、observation、非同期コマンド受付の認可はapplicationで完結する。
- applicationとagentsは相互に依存しない。
- API routeはapplicationの公開contractだけを呼ぶ。
- workerがapplication、agent、外部アダプターを組み立てる。
- CLIとStreamlitはHTTP APIだけでゲームを操作する。
- public state、timeline、LLM observationへ秘匿情報を含めない。
- 外部LLM出力はschema検証後にactionへ変換する。
- 正規faction IDとwinner IDは`village`、`werewolf`、`fox`とする。

構造規則の正本は`scripts/architecture/rules.toml`である。構造テスト、分析JSON、
評価文書、図は同じ定義を使用する。

## 作業

1. 対象のdesign文書、実装、テスト、設定を確認する。
2. 原因を責務と依存境界まで絞り、同じ原因を持つ箇所を検索する。
3. 境界変更はdesign文書と構造規則へ反映する。
4. 再現テストを追加し、最小の所有モジュールへ実装する。
5. 不要な旧path、fallback、重複を削除する。
6. formatter、lint、型、対象テスト、品質プロファイルを実行する。

UI変更では自動ブラウザーE2Eの成功後にブラウザー画面確認スキルを使い、desktopとmobileの
主要状態を操作して成果物と照合する。スキルを利用できない場合はAI画面レビューだけを
`blocked`とし、自動E2Eの結果と混同しない。

後方互換は要求された場合だけ維持する。可変値は設定または定義resourceへ置き、
安定した識別子だけを所有モジュール内で定数化する。

## コマンド

```powershell
uv run --no-project python -m scripts.environment check check
uv run --no-project python -m scripts.environment setup check
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

品質判定はfake、fixture、localhost、Compose内serviceで完結させる。package registry、
ブラウザー配布元、image registryへの接続はenvironment準備で許可する。有料providerや
任意の外部APIを品質判定へ使用しない。

## 文書

完成した仕様は`docs/design`、調査、比較、QA、引継ぎは`docs/notes`に置く。
説明は現在形の日本語を基本にし、コード識別子と外部API名は英語のまま扱う。
利用開始だけを`README.md`へ置き、具体的な開発操作は`scripts/README.md`、設定のデフォルトと
環境変数はsettings model、`src/werewolf_agent/settings/resources/defaults.toml`、
`.env.example`を正本とする。実測件数や最新結果を固定せず、品質reportへ誘導する。

## Commit

日本語のConventional Commitsに近い一行を使う。
