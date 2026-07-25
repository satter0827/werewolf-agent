# 品質管理スクリプト

## 目的

`scripts`はローカルとCIで共有するPython製の品質実行基盤です。テスト実装は
`tests`へ置き、scriptsからはpytestのCLIだけを呼び出します。

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
```

- `quick`: 日常の静的検査とunit test
- `check`: branch coverage、docs、frontend build、配布物契約、monkey、benchmark
- `release`: local Supabase、integration、React／Streamlit E2E、Docker smoke
- `deep`: 拡張探索、障害系、画面操作
- `clean`: 再生成可能なbuild、品質用一時cache、coverage、期限切れrun

`--jobs`で並列度、`--timeout`でgateごとの上限秒数を変更できます。既定の並列度は
CPU数と設定上限の小さい方です。worker数は設定上限以下、timeoutは1以上、
既定worker上限、保持日数、profile別timeout、benchmark反復下限、平均時間上限、
branch coverage下限は`pyproject.toml`の`tool.werewolf-quality`から読みます。
総合coverage下限は`tool.coverage.report.fail_under`と共有します。

`scripts.environment`はlockとtool versionのfingerprintを確認し、不足時だけPython、
Node、Supabase image、E2E image、runtime imageを準備します。品質commandは不足物を
取得せず`blocked`にします。

## 判定

状態は`passed`、`failed`、`error`、`blocked`、`skipped`です。終了値は成功が0、
品質違反が1、環境不備または実行基盤の異常が2です。`blocked`はDockerやSupabase
CLIなど、選択profileに必要なローカル環境が不足した場合に使います。timeoutは
品質違反にせず`error`として終了します。

## 成果物

成功結果は`.werewolf-agent/quality/latest/profiles/<profile>/`、個別gateは
`.werewolf-agent/quality/latest/gates/<selector>/`へ保存します。成功履歴は増やさず、
最新のJSON reportとMarkdown summaryだけを置き換えます。非成功結果は
`.werewolf-agent/quality/failures/<selector>/`へ直近3件だけ保存します。未実行gateも
`skipped`として残すため、AIと人間が同じreportから調査を開始できます。Git状態の
初期確認失敗やrunner中断も、実行済み・未完了・cleanupを含むreportを生成します。
`report.json`の`metrics`にはtest件数、総合・line・branch coverage、benchmark、
browser成果物を収録します。成果物が壊れている場合もreport生成を止めず、
`artifact_issues`へ解析理由を残し、`artifact-validation`を`error`としてCLI終了値へ
反映します。
profileごとのJUnit、coverage、benchmark、docs、frontend、package、browser成果物も
必須契約として検証するため、コマンドの0終了だけでは合格になりません。
必須成果物はrun開始後に更新されたことも検証します。docs、frontend、packageは
各ゲートで既存出力を除去してから再構築し、前回runの成果物を受理しません。

## 制約

品質実行は依存install、browser download、Docker pull、外部API呼び出しを行いません。
子processからprovider用の秘密情報と外部base URLを除外し、`WEREWOLF_LLM_PROVIDER`
を`fake`へ固定してtelemetryを無効化します。package registryとimage registryは
環境準備で使用できます。Playwrightは外部requestの試行も
失敗にし、Chromiumの背景通信と更新確認を無効化します。E2Eは既存のReact／Streamlit
Playwright suiteをcontainer内で共有し、子processの出力と画像をrun固有領域へ保存して
終了時に伏せ字化します。
`preflight_supabase`は`.env`を変更せず、取得した接続情報をmigrationと`doctor`へだけ
渡します。API起動が必要な`setup-options`はE2Eで確認します。
品質runごとの一時`SUPABASE_HOME`を使い、通常開発用の認証profileや更新cacheを
読みません。
Supabase CLIの出力からは公開キー、URL、DB接続先だけを許可し、service-role値は
引き渡しません。Supabase CLIは`2.104.0`に固定し、対応するDocker imageは
environment準備で取得します。
Release/Deepは固有project IDと未使用portの隔離DBを使い、
品質用session、container、volume、project設定を終了時に削除します。Docker buildは
runner開始前に行い、runner中のsmokeはnetworkなしで実行します。timeoutやrunner割り込み時は子孫processを含めて停止し、
品質用Supabaseと一時Docker imageのcleanupを試みます。OneDrive上の再生成可能な
ディレクトリ削除は、一時的な競合に限って短時間再試行します。成功結果の置換と
非成功結果の整理はrun確定時に実行します。
