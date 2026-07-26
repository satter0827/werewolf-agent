# Werewolf Agent

LLM agent を人狼ゲームの player として動かす Python backend です。決定的な domain
core がゲームルールと完全状態を管理し、通常の HTTP API を通じて公開状態、public
timeline、認証した player 本人の observation を提供します。完全状態を返す reveal
は、設定で有効化した管理者専用 API に分離します。

React、CLI、Streamlit は同じ API contract を使います。Supabase は Auth、永続化、
operation queue を担当し、worker が自動進行と LLM provider を実行します。既定の
FakeListLLM は外部 API と credential を必要としません。

## セットアップ

Python 3.11 以上 3.15 未満、uv、Node.js、Docker、Supabase CLI を使用します。

```powershell
uv run --no-project python -m scripts.environment setup check
uv run --no-sync werewolf-agent system doctor
```

local Supabase を含む事前確認:

```powershell
uv run --no-sync python -m scripts.supabase preflight
```

## 実行

CLI で再現可能な game を実行します。

```powershell
uv run --no-sync werewolf-agent game play --preset standard_6 --seed 1
```

設定を編集する場合は、完全なsetup documentをTOMLへ出力してから検証します。

```powershell
uv run --no-sync werewolf-agent setup export --preset standard_6 --output-file game-setup.toml
uv run --no-sync werewolf-agent setup validate game-setup.toml
uv run --no-sync werewolf-agent game create --setup-file game-setup.toml --seed 1
```

各 process は console entrypoint または `.vscode/launch.json` から起動できます。

```powershell
uv run --no-sync werewolf-agent-worker run
uv run --no-sync streamlit run src/werewolf_agent/clients/streamlit/app.py
docker compose --profile dev up --build
```

React、API、worker、Supabaseは`React Stack`、Streamlit、API、worker、Supabaseは
`Streamlit Stack`からまとめて起動できます。Stackを停止すると、Stackが使用した
ローカルSupabaseも停止します。

## 設計

| Path | 責務 |
| --- | --- |
| `src/werewolf_agent/domain` | 集約、状態、イベント、ルール policy |
| `src/werewolf_agent/application` | stateless application、DTO、repository port |
| `src/werewolf_agent/agents` | provider非依存の観測、意思決定、player port |
| `src/werewolf_agent/adapters` | HTTP client、Supabase、LangChain、agent接続 |
| `src/werewolf_agent/api` | FastAPI、認証、認可、composition root |
| `src/werewolf_agent/worker` | operation queue、自動進行、LLM実行 |
| `src/werewolf_agent/clients` | CLI、Streamlit |
| `src/werewolf_agent/contracts` | 外部 wire schema と安全な error |
| `src/werewolf_agent/settings` | runtime設定、定義resourceの検証 |
| `frontend` | React UI と generated OpenAPI client |

`Game`だけがゲーム状態を変更します。applicationはdomain操作と保存を調整し、画面は
合法手、フェーズ、勝敗を再計算しません。agentsとapplicationは互いに依存せず、
`adapters/agents/game_driver.py` が observation、decision、action を変換します。

要件から運用までの説明は [Sphinx 設計書](docs/index.md) を参照してください。

## 文書と構造分析

文書の構造検査と Sphinx build は品質 runner から独立して実行できます。

```powershell
uv run --no-sync python -m scripts.docs inspect
uv run --no-sync python -m scripts.docs build
uv run --no-sync python -m scripts.architecture
```

HTMLは`.werewolf-agent/build/docs/index.html`、機械可読な依存graph、schema、評価、
SVGは`.werewolf-agent/build/architecture`に生成されます。同じ操作をVS Codeの
`Docs: Build`、`Architecture: Analyze` taskから実行できます。

## 検証

```powershell
uv run --no-sync python -m scripts.quality quick
uv run --no-sync python -m scripts.quality check
uv run --no-sync python -m scripts.quality release
uv run --no-sync python -m scripts.quality deep --confirm-deep
uv run --no-sync python -m scripts.quality gate python-static
uv run --no-sync python -m scripts.quality list
```

`scripts.quality` は品質 gate 全体の順序、timeout、report を管理します。docs と
architecture の個別処理は専用 script が所有し、品質 runner はその入口を呼びます。
結果は`.werewolf-agent/quality`に保存されます。最新成功runはreportだけでなく、event、
log、JSON/HTML test結果、coverage、画面、manifestを含むreview bundleです。
`manifest.json`のSHA-256とproducerから証拠の出所と実在を確認できます。

VS Codeでは「実行とデバッグ」の`Verify: Quality`からlevelを選び、
`Review: Evidence`からUI、Gameplay、Local LLMの読解用証拠を選びます。起動、report表示、
所有resourceのcleanupも同じ候補から実行でき、commandの手入力は不要です。
UIはdesktop/mobileのsetup、gameplay、observer、空の履歴、完了結果、履歴、設定と代表的な
loading/errorを画像と一覧画像で残します。Gameplayは現在のゲーム定義からseed固定で完走し、設定、操作列、公開
timeline、終局をJSONへ保存します。面白さや見た目に点数や自動合否は付けません。

環境準備はfile lockの内側でlockに従って依存、browser、imageを準備します。品質判定は
fake、fixture、localhost、Compose内serviceだけを使用し、有料LLM providerや任意の
外部APIへ依存しません。利用者がアプリ運用で有料providerを設定することはできますが、
品質・review processはcredentialを除去します。online auditは`Dependencies: Audit`から
明示的に実行します。

## 運用境界

repository は設定検証、migration、process 起動、health signal、構造化ログ、品質
artifact を提供します。本番 deployment、backup、monitoring rule、通知、credential
rotation は外部運用基盤が管理します。

## License

MIT License
