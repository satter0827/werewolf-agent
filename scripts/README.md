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
uv run --no-sync python -m scripts.quality check --base-ref origin/develop --head-ref HEAD --fresh
uv run --no-sync python -m scripts.quality release --fresh
uv run --no-sync python -m scripts.quality deep --confirm-deep --fresh
uv run --no-sync python -m scripts.quality gate python-static
uv run --no-sync python -m scripts.versioning inspect
uv run --no-sync python -m scripts.versioning suggest --base-ref origin/main --head-ref HEAD
uv run --no-sync python -m scripts.versioning bump patch --base-ref origin/main --head-ref HEAD --dry-run
uv run --no-sync python -m scripts.versioning bump patch --base-ref origin/main --head-ref HEAD
uv run --no-sync python -m scripts.versioning check --base-ref origin/main --head-ref HEAD
uv run --no-sync python -m scripts.quality gate ruff mypy
uv run --no-sync python -m scripts.quality list
uv run --no-sync python -m scripts.quality auto --explain
uv run --no-sync python -m scripts.quality clean
uv run --no-sync python -m scripts.quality report open
uv run --no-sync python -m scripts.quality cleanup
uv run --no-sync python -m scripts.quality cleanup --confirm DELETE
```

`suggest`はmainとの差分に含まれるConventional Commitから`patch`、`minor`、`major`を提案するが、
versionを変更しない。変更levelは利用者が決定し、`bump`へ明示する。`bump`はcommit済み、stage済み、
未stage、未追跡の変更pathをregistryの所有範囲へ対応付け、productと影響を受ける境界だけを更新する。
同じlevelでの再実行は変更を増やさず、異なる手動versionが既にある場合は上書きせず停止する。
最初に`--dry-run`で対象を確認する。

| プロファイル | 判定範囲 |
| --- | --- |
| `auto` | `scripts/quality/impact.toml`により変更pathからプロファイルまたは部分gateを選ぶ |
| `focus` | architecture、format、lint、型、unit、軽量stateful |
| `check` | Focus、coverage、offline integration、docs、OpenAPI、Schemathesis、package |
| `release` | Check、local Supabase lint、API、worker、Streamlit E2E、container |
| `deep` | 長時間stateful、fault injection、benchmark観測 |

プロファイル名を直接指定した場合は差分にかかわらず全体を実行する。`--fresh`は再利用可能な
成功gateも実行し直す。`auto --explain`は選定理由、stage、再利用候補を表示して終了する。
`--base-ref`と`--head-ref`はcommit済みのPR差分を変更影響とreportへ関連付ける。明示したrefは
Version gateへそのまま渡す。baseを省略した場合だけ、Version gateはリリース基準の`origin/main`を
使用し、reportの実コマンドにも既定refを明示する。
`HEAD`以外のheadを指定する場合はworkspaceをcleanにする。未commitの変更を検査する場合は
`--head-ref HEAD`を使用し、任意commitへ別treeのworkspace差分を合成しない。

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

短期branchは`develop`から作成し、PRで取り込む。`develop`向けPRはPython 3.12のCheckだけを
必須とする。`main`向けPRは`develop`から作成し、Deepと対応Python版の互換性検査を必須とする。

PR前のLinux検証ではbranchをremoteへpushし、GitHub Actionsの`Quality`から`Run workflow`を
選び、対象branchを指定する。手動実行は選択branchの`HEAD`に対して`Develop / Check`を実行する。
品質reportのrevisionがbranchのcommitと一致することを確認する。

手動Checkはbranch単体を検証し、PR Checkは`develop`との仮想mergeを検証する。最終的なmerge判定は
PR Checkを使用する。Deepはローカル、毎晩の`develop`、`main`向けPRで実行する。

すべてのPRはmerge commitを使用する。GitHub rulesetの正本は`.github/rulesets`に置き、remoteへ
適用した後にGitHub APIから読み戻して確認する。夜間Deepは毎日03:17 JSTに変更を検知し、
月曜JSTだけは変更や成功cacheの有無にかかわらず実行する。手動の`nightly-deep`も強制実行する。
夜間Deepは早期検知に使用し、通常のmerge条件には含めない。

AIはPRの調査、作成、修正、通常コメント、inline `COMMENT`を担当する。`develop`向けPRは必須checkと
未解決指摘を最新head SHAで確認し、そのcommitへ判断を記録してmerge commitで取り込める。正式な
レビュー判断とレビューAPIの`COMMENT`は`commit_id`、merge時は`expected_head_sha`へ同じ最新head SHAを
指定する。通常コメントはレビューAPIと分離する。同じGitHubアカウントの自己承認が拒否される場合は、
commitへ固定した`COMMENT`に判断と根拠を残す。
`main`向けPRの正式な承認とmerge、レビュー会話の解決、auto-mergeは人間が担当する。リポジトリ固有の
`.codex/hooks.json`は構造化GitHub connectorの禁止操作を実行前に拒否し、hook変更後は新しいCodex
sessionで再信頼する。`main`と`develop`のRulesetで`required_approving_review_count`を0とする設定は、
同一GitHubアカウントによる単独開発を停止させないための意図的な設定である。mainへの最終判断では
人間が未解決会話と必須checkを確認する。

このhookはshellコマンドを解析しない。Bash、PowerShell、cmdの文法を部分的に再実装せず、型付きの
GitHub connector入力だけを判定する。これはGitHub側の権限制御ではないため、branch保護の正本は
Rulesetとrequired checksである。CodexはCLI、API、ブラウザー、hook対象外のhosted tool、外部programへ
切り替えて禁止操作を回避しない。禁止操作が必要な場合は人間へ引き渡す。

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
