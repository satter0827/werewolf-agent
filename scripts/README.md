# 品質管理スクリプト

## 目的

`scripts`はローカルとCIで共有するPython製の品質実行基盤です。`tests/unit`は通常の
単体テスト、`tests/integration`は複数moduleを接続したコード全体のテストを所有します。
Browser、Compose、環境準備などのリリース品質scenarioは`scripts`が所有します。

## 実行方法

```bash
python -m scripts.environment ensure check
python -m scripts.quality quick
python -m scripts.quality check
python -m scripts.quality release
python -m scripts.quality deep --confirm-deep
python -m scripts.quality gate python-static
python -m scripts.quality gate ruff mypy
python -m scripts.quality list
python -m scripts.quality clean
python -m scripts.supabase preflight
python -m scripts.agents preflight
python -m scripts.agents run --provider fake --suite standard
python -m scripts.agents run --provider local --suite smoke
python -m scripts.agents run --provider local --suite standard
python -m scripts.agents local-ui
```

- `quick`: architecture、format、lint、型、unit、軽量Hypothesis
- `check`: Quick、offline integration、coverage観測、docs、OpenAPI、Schemathesis、build
- `release`: Check、local Supabase integration、Streamlit E2E、Docker smoke
- `deep`: 長時間stateful、fault injection、benchmark観測
- `clean`: 再生成可能なbuild、品質用一時cache、coverage、期限切れrun

`scripts.agents`は品質判定から独立したAgent reviewです。通常は画面を使わず、同じAgent
graphをFakeまたはLocal LLMで固定scenarioへ通します。`local-ui`だけが明示的にStreamlitを
起動し、認証済みAPI driverでLocal LLM gameを進行します。結果は
`passed`、`degraded`、`failed`、`blocked`、`error`で、
修復またはfallbackを伴う完走は`degraded`です。standardは開始時とpreset完了時に
checkpointを更新し、完了または中断時に最終状態を確定します。
`run --suite standard --preset <id>`は指定presetだけを固定順で実行し、複数指定できます。

`--jobs`で並列度、`--timeout`でgateごとの上限秒数を変更できます。既定の並列度は
CPU数と設定上限の小さい方です。worker数は設定上限以下、timeoutは1以上、
既定worker上限、保持件数、profile別timeout、benchmark反復下限は`pyproject.toml`の
`tool.werewolf-quality`から読みます。coverageとbenchmarkは観測値として保存し、根拠の
ない数値閾値では合否を決めません。

`scripts.environment`はlockとtool versionのfingerprintを確認し、不足時だけPython依存を同期します。
release環境ではSupabase image、E2E image、runtime imageも準備します。品質commandは不足物を
取得せず`blocked`にします。release系の準備済み判定は保存済みmarkerだけでなく、現在の
Docker contextでdaemonと全必須imageの実在も確認します。Docker Desktopのresetやcontext変更で
imageが失われた場合、次の`ensure`は自動的に再準備します。

## 判定

状態は`passed`、`failed`、`error`、`blocked`、`skipped`です。終了値は成功が0、
品質違反が1、環境不備または実行基盤の異常が2です。`blocked`はDockerやSupabase
CLIなど、選択profileに必要なローカル環境が不足した場合に使います。timeoutは
品質違反にせず`error`として終了します。

## 成果物

成功結果は`.werewolf-agent/quality/latest/profiles/<profile>/`、個別gateは
`.werewolf-agent/quality/latest/gates/<selector>/`へ保存します。成功履歴は増やさず、
report、summary、event、log、test結果、coverage、画面、manifestを含む一式を
置き換えます。非成功結果は
`.werewolf-agent/quality/failures/<selector>/`へ直近3件だけ保存します。未実行gateも
`skipped`として残すため、AIと人間が同じreportから調査を開始できます。Git状態の
初期確認失敗やrunner中断も、実行済み・未完了・cleanupを含むreportを生成します。
`report.json`の`metrics`にはtest件数、総合・line・branch coverage、benchmark、
browser成果物を収録します。成果物が壊れている場合もreport生成を止めず、
`artifact_issues`へ解析理由を残し、`artifact-validation`を`error`としてCLI終了値へ
反映します。
profileごとのJUnit、coverage、benchmark、docs、package、browser成果物も
必須契約として検証するため、コマンドの0終了だけでは合格になりません。
必須成果物はrun開始後に更新されたことも検証します。docsとpackageは
各ゲートで既存出力を除去してから再構築し、前回runの成果物を受理しません。

## 制約

品質実行は依存install、browser download、Docker pull、外部API呼び出しを行いません。
子processからprovider用の秘密情報と外部base URLを除外し、`WEREWOLF_LLM_PROVIDER`
を`fake`へ固定し、Local／OpenAI／worker provider設定も除去してtelemetryを無効化します。package registryとimage registryは
環境準備で使用できます。Playwrightは外部requestの試行も
失敗にし、Chromiumの背景通信と更新確認を無効化します。E2EはPython PlaywrightのStreamlit
scenarioをcontainer内で実行し、子processの出力と画像をrun固有領域へ保存して
終了時に伏せ字化します。
`preflight_supabase`は`.env`を変更せず、取得した接続情報をmigrationと`doctor`へだけ
渡します。API起動が必要な`setup-options`はE2Eで確認します。
品質runごとの一時`SUPABASE_HOME`を使い、通常開発用の認証profileや更新cacheを
読みません。
Supabase CLIの出力からは公開キー、URL、DB接続先だけを許可し、service-role値は
引き渡しません。Supabase CLIは`2.104.0`に固定し、対応するDocker imageは
environment準備で取得します。
Release/Deepは固定された品質用Compose projectを一組だけ使い、所有labelで識別した
session、container、volumeを終了時に削除します。Docker buildは
runner開始前に行い、runner中のsmokeはnetworkなしで実行します。timeoutやrunner割り込み時は子孫processを含めて停止し、
品質用Supabaseと一時Docker imageのcleanupを試みます。OneDrive上の再生成可能な
ディレクトリ削除は、一時的な競合に限って短時間再試行します。成功結果の置換と
非成功結果の整理はrun確定時に実行します。
