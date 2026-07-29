# リポジトリ運用スクリプト

`scripts`は、ローカル、CI、AIが共有する再現可能な開発操作を所有する。品質runnerは
個別検査を再実装せず、環境準備、docs、architecture、contracts、ブラウザー、Supabaseなどの
専用入口を組み合わせる。

## 環境準備

依存取得は`scripts.environment setup`だけが行う。`check`は現在のfingerprintと
実行能力を読み取り専用で検査し、依存、image、containerを変更しない。品質コマンド自身は
package、ブラウザー、imageを取得せず、前提が不足する場合は`blocked`にする。

```powershell
uv run --no-project python -m scripts.environment check python
uv run --no-project python -m scripts.environment check development
uv run --no-project python -m scripts.environment check quality
uv run --no-project python -m scripts.environment setup python
uv run --no-project python -m scripts.environment setup development
uv run --no-project python -m scripts.environment setup quality
```

`python`はPython依存、`development`はDockerと開発用Supabase、`quality`はBuildx、品質用image、
隔離Supabaseまでを対象にする。要求するSupabase CLI版は`scripts/supabase/constants.py`を正本とする。
`setup development|quality`は隔離Supabase projectで必要imageを準備し、project IDとworkdirを
指定して停止する。Docker Desktopは自動起動しない。

## 品質プロファイル

```powershell
uv run --no-sync python -m scripts.quality auto
uv run --no-sync python -m scripts.quality focus
uv run --no-sync python -m scripts.quality check --fresh
uv run --no-sync python -m scripts.quality check --base-ref origin/develope --head-ref HEAD --fresh
uv run --no-sync python -m scripts.quality release --fresh
uv run --no-sync python -m scripts.quality deep --confirm-deep --fresh
uv run --no-sync python -m scripts.quality gate python-static
uv run --no-sync python -m scripts.quality gate ruff mypy
uv run --no-sync python -m scripts.quality list
uv run --no-sync python -m scripts.quality auto --explain
uv run --no-sync python -m scripts.quality clean
uv run --no-sync python -m scripts.quality report open
uv run --no-sync python -m scripts.quality cleanup
uv run --no-sync python -m scripts.quality cleanup --confirm DELETE
```

| プロファイル | 判定範囲 |
| --- | --- |
| `auto` | `scripts/quality/impact.toml`により変更pathからプロファイルまたは部分gateを選ぶ |
| `focus` | architecture、format、lint、型、unit、軽量stateful |
| `check` | Focus、coverage、offline integration、docs、OpenAPI、Schemathesis、package |
| `release` | Check、local Supabase lint、API、worker、Streamlit E2E、container |
| `deep` | 長時間stateful、fault injection、benchmark観測 |

プロファイル名を直接指定した場合は差分にかかわらず全体を実行する。`--fresh`は再利用可能な
成功gateも実行し直す。`auto --explain`は選定理由、stage、再利用候補を表示して終了する。
`--base-ref`と`--head-ref`はcommit済みのPR差分を変更影響とreportへ関連付ける。

状態は`passed`、`failed`、`blocked`、`error`、`skipped`である。終了値は成功が0、品質違反が1、
環境不備または実行基盤異常が2である。coverage、benchmark、ゲームバランスは観測値として保存し、
根拠のない閾値だけで不合格にしない。

## 成果物

有限の環境操作は`.werewolf-agent/operations/<kind>/<run-id>`へ`report.json`、`summary.md`、
`manifest.json`、失敗stageのredactedログを保存する。常駐プロセスのJSONLは
`.werewolf-agent/logs/application`へ分離する。全体を調べる場合は次を実行する。

```powershell
uv run --no-sync python -m scripts.diagnostics collect
```

診断viewは`.werewolf-agent/diagnostics/current`へ生成され、既存ログと成果物を複製せず
pathとSHA-256で参照する。

`clean`は品質reportを含む再生成可能な成果物だけを削除する。`cleanup`は品質所有のCompose project、
container、volume、隔離Supabaseのcontainer、volume、networkを列挙し、
`--confirm DELETE`がある場合だけ削除する。

最新試行は成否に関係なく`.werewolf-agent/quality/profiles/<profile>/current`へ保存する。
以前の試行は`.werewolf-agent/quality/history/<profile>/<run-id>`へ移動し、最終成功は
`profiles/<profile>/last-passed.json`が指す。

各runは`report.json`、`summary.md`、`events.jsonl`、`manifest.json`と、実行したgateのログ、
テスト結果、coverage、ブラウザー成果物を持つ。manifestのproducer、分類、MIME、size、SHA-256で
証拠の出所と実在を確認する。未完了gateも`skipped`として残し、runner中断や初期検査失敗も
reportへ確定する。

`report.json`は検証したrevisionとtree、base、head、merge-base、変更path、workspace fingerprintを
保持する。runnerは全gateとresource cleanupの終了後にリポジトリ状態を再取得し、実行中の副作用を
`repository-stability`で判定する。

## BranchとCI

短期branchは`develope`から作成し、PRで取り込む。`develope`向けPRはPython 3.12のCheckだけを
必須とする。`main`向けPRは`develope`から作成し、Deepと対応Python版の互換性検査を必須とする。

PR前のLinux検証ではbranchをremoteへpushし、GitHub Actionsの`Quality`から`Run workflow`を
選び、対象branchを指定する。手動実行は選択branchの`HEAD`に対して`Develope / Check`を実行する。
品質reportのrevisionがbranchのcommitと一致することを確認する。

手動Checkはbranch単体を検証し、PR Checkは`develope`との仮想mergeを検証する。最終的なmerge判定は
PR Checkを使用する。Deepはローカル、週次`develope`、`main`向けPRで実行する。

すべてのPRはmerge commitを使用する。GitHub rulesetの正本は`.github/rulesets`に置き、remoteへ
適用した後にGitHub APIから読み戻して確認する。週次Deepは`develope`の早期検知に使用し、通常の
merge条件には含めない。

## ブラウザーE2E

ブラウザーjourney、state、device、capture名の正本は`scripts/browser/catalog.toml`である。
PlaywrightはPythonからStreamlitを操作し、外部request、console、accessibility、主要状態を検査する。

```powershell
uv run --no-sync python -m scripts.browser --journey play --state finished --device desktop
uv run --no-sync python -m scripts.browser --capture gameplay-complete --device desktop
```

通常の直接実行は`.werewolf-agent/reviews/browser`へ保存する。品質プロファイル内ではrun固有の
ブラウザー成果物としてmanifestへ登録される。認証情報を含み得るtraceとnative reportはprivate、
画面、console、network要約はpublicとして分離する。

## エージェントレビュー

エージェントレビューは製品品質の合否から独立し、Fakeまたは明示したloopback Local LLMで会話、判断、
ゲームバランスを読むための証拠を作る。

```powershell
uv run --no-sync python -m scripts.agents preflight
uv run --no-sync python -m scripts.agents run --provider fake --suite standard
uv run --no-sync python -m scripts.agents run --provider local --suite smoke
uv run --no-sync python -m scripts.agents local-ui
uv run --no-sync python -m scripts.review ui
uv run --no-sync python -m scripts.review gameplay
uv run --no-sync python -m scripts.review local-llm
```

Fakeと実LLMは同じrequest、応答正規化、schema検証、合法手検証、fallbackを通る。
Local smokeはloopbackだけを許可し、一局完走とStreamlitの統合確認は`local-ui`へ分離する。
結果は`.werewolf-agent/reviews/agents`へ`report.json`、`summary.md`、`manifest.json`として保存し、
public timelineとprivate traceを分離する。active markerを持つ実行中runは保持処理の対象外である。

## 個別入口

```powershell
uv run --no-sync werewolf-agent system doctor
uv run --no-sync python -m scripts.docs inspect
uv run --no-sync python -m scripts.docs build
uv run --no-sync python -m scripts.architecture
uv run --no-sync python -m scripts.contracts.openapi
uv run --no-sync python -m scripts.supabase serve --stop-on-exit
```

品質プロセスはprovider credentialと外部base URLを除去し、Fakeアダプター、localhost、Compose内service
だけを使用する。registryやブラウザー配布元への接続は環境準備に限定する。品質用プロセス、
container、volumeだけを所有labelでcleanupし、開発用または他projectのresourceを変更しない。
