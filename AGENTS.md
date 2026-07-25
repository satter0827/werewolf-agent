# AGENTS.md

このリポジトリで作業する AI coding agent の共通規則です。下位 directory に
`AGENTS.md` がある場合は、その範囲で下位の規則を優先します。

## システム

Werewolf Agent は LLM agent を人狼ゲームの player として動かす Python backend
です。決定的な domain core が完全状態を管理し、通常の利用者境界には公開状態、
public timeline、認証した player 本人の observation だけを返します。完全状態の
reveal は設定で有効化した管理者専用 API に隔離します。

## 最初に読む文書

- 利用と検証: `README.md`
- 要件と範囲: `docs/design/requirements.md`
- 依存方向: `docs/design/architecture.md`
- domain: `docs/design/domain.md`
- 開発: `docs/design/development.md`
- Sphinx 入口: `docs/index.md`
- 断片的な調査記録: `docs/notes/`

## 責務と依存方向

| Path | 責務 |
| --- | --- |
| `domain` | 集約、状態、イベント、rule policy |
| `usecase` | stateless handler、DTO、repository port、projection |
| `agents` | provider 非依存の観測、意思決定、player port |
| `adapters` | GameClient、Supabase、agents 接続、外部 service |
| `api` | HTTP、認証、認可、composition root |
| `interfaces` | CLI、Streamlit、worker |
| `contracts` | Pydantic 外部契約、安全な error |
| `configuration` | settings、definition、resource、message |
| `observability` | logging と実行 context |
| `security` | redaction |

次の境界を維持します。

- `Game` だけがゲーム状態を変更する。
- domain は他層、file I/O、環境変数、logging、database、LLM provider に依存しない。
- usecase は agents、adapters、interfaces、logging に依存しない。
- agents は domain と usecase に依存しない。
- `adapters/agents/game_driver.py` だけが usecase と agents を変換して接続する。
- React、CLI、Streamlit は HTTP API だけで操作し、ゲームルールを再計算しない。
- CLI と Streamlit は public contract と `GameClient` port を使う。
- React の Supabase 接続は Auth に限定し、game 通信は generated client を使う。
- public state、timeline、LLM observation に閲覧者が知り得ない情報を含めない。
- LLM 出力は schema で検証してから action へ変換する。

境界定義は `scripts/architecture/definition.py` を唯一の機械可読な source とし、構造テスト、
JSON、schema、評価文書、SVG から共用します。

## 作業

1. 要求に近い設計書、実装、テスト、設定を確認する。
2. 原因を責務と依存境界まで絞り、同じ原因を持つ箇所を検索する。
3. 大きな境界変更は設計書へ反映してから実装する。
4. 再現テストを追加し、最小の責務へ変更する。
5. 不要な旧 path、fallback、重複を削除する。
6. formatter、lint、型、対象テスト、品質 profile を実行する。

後方互換は要求された場合だけ維持します。無関係な refactor、整形だけの差分、
ユーザーや他 agent の未コミット変更の巻き戻しを混ぜません。

設定、provider、model、database、ログ、retry は安全な default を持つ設定値にします。
設定追加時は `.env.example`、検証、文書、テストを揃えます。

## コマンド

```powershell
uv sync --frozen --all-groups --all-extras
uv run --no-sync werewolf-agent doctor
uv run --no-sync ruff format --check .
uv run --no-sync ruff check --no-cache .
uv run --no-sync mypy --no-incremental src
uv run --no-sync pytest
```

品質 profile:

```powershell
uv run --no-sync python -m scripts.quality quick
uv run --no-sync python -m scripts.quality check
uv run --no-sync python -m scripts.quality release
uv run --no-sync python -m scripts.quality deep --confirm-deep
```

文書と構造分析:

```powershell
uv run --no-sync python -m scripts.docs inspect
uv run --no-sync python -m scripts.docs build
uv run --no-sync python -m scripts.architecture
```

`scripts.quality` は全品質 gate の orchestration だけを担当します。docs の検査と
Sphinx build は `scripts.docs`、構造評価と可視化は `scripts.architecture` に置き、
単独実行可能にします。

VS Code の task は反復実行する build と検査、launch は debugger を使う process と
test に使います。どちらも上記と同じ Python module または console entrypoint を
呼び、別の処理を実装しません。

## テスト

- ルール、勝敗、投票、夜行動は domain unit test を優先する。
- bug 修正には可能な限り再現テストを追加する。
- 外部 LLM は通常テストから分離し、fake、mock、fixture を使う。
- ランダム性は seed を固定する。
- architecture test で import 境界と cycle を検査する。
- docs test は lifecycle、到達性、公開 API、docstring 抑制を検査し、文章量を固定しない。

## 文書と docstring

完成した仕様は `docs/design`、断片的な調査と引き継ぎは `docs/notes` に置きます。
README は利用者の入口に保ちます。説明は日本語を基本にし、コード識別子と外部 API
名は英語のまま扱います。時点や編集経緯を表す文言を設計本文へ入れません。

Sphinx で公開する module、class、function、method には Google style の docstring を
記述します。引数、戻り値、例外が存在する場合は実装と一致させます。短い説明へ
定型 section を無理に追加せず、`noqa` で docstring 検査を回避しません。

## セキュリティと観測

- `.env`、API key、token、秘密鍵、実データを commit しない。
- credential を応答、timeline、prompt、ログへ出さない。
- private state を通常応答、timeline、ログへ出さず、LLM には player の観測範囲だけを渡す。
- 完全状態は管理者認可と専用設定を通過した reveal 応答だけに許可する。
- 外部入力を未検証のまま prompt、path、shell command に渡さない。
- usecase と domain はログを出さず、interfaces と adapters が外部境界で記録する。
- ログ名は `worker.jsonl` のように機能名を使い、起動手段や作業者名を含めない。

共有する report と生成物は `.werewolf-agent`、再利用しない cache は OS の一時
directory に置きます。品質 runner 中に依存取得、browser download、Docker pull、
online audit、外部 API 呼び出しを行いません。

## 問題が残る場合

不足する依存、権限、外部 service、確定していない仕様、完了範囲、実行コマンド、
判断が必要な選択肢を残します。外部 API がなくても実装と検証を進められる fake を
優先します。

## Commit

日本語の Conventional Commits に近い一行を使います。

- `feat: Supabase worker の queue 処理を追加`
- `fix: public timeline から秘匿情報を除外`
- `docs: 開発ライフサイクルを体系化`
