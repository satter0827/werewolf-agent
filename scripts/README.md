# Repository運用スクリプト

`scripts`は、ローカル、CI、AIが共有する再現可能な開発操作を所有します。品質runnerは
個別検査を再実装せず、環境準備、docs、architecture、contracts、Browser、Supabaseなどの
専用入口を組み合わせます。

## 環境準備

依存取得は`scripts.environment`だけが行います。`ensure`は現在のfingerprintを検査し、
不足時だけ対応する`setup`を実行します。品質command自身はpackage、browser、imageを取得せず、
前提が不足する場合は`blocked`にします。

```powershell
uv run --no-project python -m scripts.environment ensure auto
uv run --no-project python -m scripts.environment ensure check
uv run --no-project python -m scripts.environment ensure release
uv run --no-project python -m scripts.environment ensure deep
```

release系では現在のDocker context、daemon、Supabase、E2E、runtime imageの実在も確認します。
明示的に環境を再構築する場合だけ`setup check|release|deep`を使用します。

## 品質profile

```powershell
uv run --no-sync python -m scripts.quality auto
uv run --no-sync python -m scripts.quality focus
uv run --no-sync python -m scripts.quality check --fresh
uv run --no-sync python -m scripts.quality release --fresh
uv run --no-sync python -m scripts.quality deep --confirm-deep --fresh
uv run --no-sync python -m scripts.quality gate python-static
uv run --no-sync python -m scripts.quality gate ruff mypy
uv run --no-sync python -m scripts.quality list
uv run --no-sync python -m scripts.quality auto --explain
uv run --no-sync python -m scripts.quality clean
```

| Profile | 判定範囲 |
| --- | --- |
| `auto` | `scripts/quality/impact.toml`により変更pathからprofileまたは部分gateを選ぶ |
| `focus` | architecture、format、lint、型、unit、軽量stateful |
| `check` | Focus、coverage、offline integration、docs、OpenAPI、Schemathesis、package |
| `release` | Check、local Supabase、API、worker、Streamlit E2E、container |
| `deep` | 長時間stateful、fault injection、benchmark観測 |

profile名を直接指定した場合は差分にかかわらず全体を実行します。`--fresh`は再利用可能な
成功gateも実行し直します。`auto --explain`は選定理由、stage、再利用候補を表示して終了します。

状態は`passed`、`failed`、`blocked`、`error`、`skipped`です。終了値は成功が0、品質違反が1、
環境不備または実行基盤異常が2です。coverage、benchmark、ゲームバランスは観測値として保存し、
根拠のない閾値だけで不合格にしません。

## 成果物

最新試行は成否に関係なく`.werewolf-agent/quality/profiles/<profile>/current`へ保存します。
以前の試行は`.werewolf-agent/quality/history/<profile>/<run-id>`へ移動し、最終成功は
`profiles/<profile>/last-passed.json`が指します。

各runは`report.json`、`summary.md`、`events.jsonl`、`manifest.json`と、実行したgateのlog、
test結果、coverage、Browser成果物を持ちます。manifestのproducer、分類、MIME、size、SHA-256で
証拠の出所と実在を確認します。未完了gateも`skipped`として残し、runner中断や初期検査失敗も
reportへ確定します。

## Browser E2E

Browser journey、state、device、capture名の正本は`scripts/browser/catalog.toml`です。
PlaywrightはPythonからStreamlitを操作し、外部request、console、accessibility、主要状態を検査します。

```powershell
uv run --no-sync python -m scripts.browser --journey play --state finished --device desktop
uv run --no-sync python -m scripts.browser --capture gameplay-complete --device desktop
```

通常の直接実行は`.werewolf-agent/reviews/browser`へ保存します。品質profile内ではrun固有の
Browser成果物としてmanifestへ登録されます。認証情報を含み得るtraceとnative reportはprivate、
画面、console、network要約はpublicとして分離します。

## Agent review

Agent reviewは製品品質の合否から独立し、Fakeまたは明示したloopback Local LLMで会話、判断、
ゲームバランスを読むための証拠を作ります。

```powershell
uv run --no-sync python -m scripts.agents preflight
uv run --no-sync python -m scripts.agents run --provider fake --suite standard
uv run --no-sync python -m scripts.agents run --provider local --suite smoke
uv run --no-sync python -m scripts.agents local-ui
```

Fakeと実LLMは同じrequest、応答正規化、schema検証、合法手検証、fallbackを通ります。
Local smokeはloopbackだけを許可し、一局完走とStreamlitの統合確認は`local-ui`へ分離します。
結果は`.werewolf-agent/reviews/agents`へ保存し、public timelineとprivate traceを分離します。

## 個別入口

```powershell
uv run --no-sync python -m scripts.docs inspect
uv run --no-sync python -m scripts.docs build
uv run --no-sync python -m scripts.architecture
uv run --no-sync python -m scripts.contracts.openapi
uv run --no-sync python -m scripts.supabase preflight
```

品質processはprovider credentialと外部base URLを除去し、Fake adapter、localhost、Compose内service
だけを使用します。registryやbrowser配布元への接続は環境準備に限定します。品質用process、
container、volumeだけを所有labelでcleanupし、開発用または他projectのresourceを変更しません。
