# 品質ゲート

## 目的

リリース可否をローカルとCIで同じ入口から判定し、失敗原因を人間とAIが再調査できる
形で残します。品質基準、実行範囲、生成物の保存先を`quality.py`へ集約し、テスト実装
とは一方向の依存関係にします。

## 実行方法

| Level | 用途 | 既定上限 |
| --- | --- | ---: |
| `quick` | 編集中の日常確認 | 60秒/gate |
| `check` | pull request相当 | 180秒/gate |
| `release` | リリース候補 | 900秒/gate |
| `deep` | 意図的な拡張確認 | 1200秒/gate |

```bash
python -m scripts.quality quick
python -m scripts.quality check
python -m scripts.quality release
python -m scripts.quality deep --confirm-deep
```

pytest単体の既定levelも`quick`です。

```bash
pytest
pytest --test-level=check -m monkey
pytest --test-level=release -n 0 tests/integration
pytest --test-level=deep --confirm-deep -m deep -n 0 tests
```

`tests/unit`はquick、`monkey`と`benchmark`はcheck、`tests/integration`はrelease、
`deep` markerはdeepを最低levelとします。配置とmarkerが異なる場合は重い方を採用
します。選択したテストがすべてlevel外の場合、pytestは成功扱いにせず、必要levelを
表示して終了します。

worker上限、run保持日数、profile別timeout、benchmark反復下限、平均時間上限、
branch coverage下限は`pyproject.toml`の`tool.werewolf-quality`、総合coverage下限は
`tool.coverage.report.fail_under`、markerは`tool.pytest.ini_options`を唯一の設定元と
します。runnerは不足・型不正・範囲外の設定を開始前に拒否します。

## 判定

### Quick

Ruff lint・format・docstring、mypy、Python unit、scripts unit、ESLint、
Prettier、TypeScript、Vitestを実行します。unit testだけは最大4 workerで並列化し、
静的検査群とは段階を分けて多重並列を抑えます。

### Check

Quickに総合coverage 74%とbranch coverage 48%、frontend production build、
Sphinx warning-as-error、
wheel・sdist、全packaged resource、CLI／worker entrypoint、64 seedのDomain monkey、
core benchmark、
tracked file非変更を追加します。

### Release

Checkに空のlocal Supabaseへのmigration、別利用者とrevealを拒否するRLSの実評価、
queue再送の冪等性、Fake LLM workerによるゲーム作成と進行、package integration、
React／Streamlit desktop/mobile、事前構築済みDocker runtimeの非root smokeを追加します。
Supabaseは開発用projectを再利用せず、`.werewolf-agent/db/quality/<run-id>`へ設定と
migrationを複製し、固有project IDと未使用portで起動します。共有DBとbrowserを使う
integrationは直列です。

### Deep

Releaseに256 seedのDomain探索、複数workerの同時claim、worker停止後の再取得、
game row lock timeout、計算中のversion競合拒否、Data API/poll timeout後の再実行、
再読込を含む状態認識型の画面探索、browser session消失後の復帰、keyboard/focusを
追加します。profileとpytestの両方で明示確認が必要です。

状態は`passed`、`failed`、`error`、`blocked`、`skipped`です。終了値は成功0、
品質違反1、環境不備または実行基盤異常2です。gate timeoutはテスト不合格ではなく
`error`として扱います。

## 成果物

```text
.werewolf-agent/
├── build/{docs,frontend,package,docker}/
├── cache/
├── coverage/
├── db/
├── logs/
├── qa/
└── quality/
    ├── latest.json
    └── runs/<run-id>/
        ├── report.json
        ├── events.jsonl
        ├── summary.md
        ├── logs/
        ├── test-results/
        ├── coverage/
        ├── benchmarks/
        └── browser/
```

各runにはJUnit XML、coverage XML/HTML、benchmark JSON、browser画像も保存します。
`report.json`にはテスト件数、総合・line・branch coverage、benchmark、browser成果物を
構造化した`metrics`と、成果物を解析できなかった場合の`artifact_issues`を保存します。
成果物を解析できない場合は`artifact-validation`を`error`にして、report、latest、
CLI終了値を同じ判定にします。同じ指標を`summary.md`にも表示します。途中で停止した
場合も未実行gateを`skipped`としてreportへ残し、失敗理由とgate別logをsummaryから
辿れます。Git working treeの初期確認に失敗した場合やrunnerが中断された場合も、
runnerの`error`、未完了gate、cleanup結果を同じreportへ保存します。

成果物の存在もprofile別に検証します。QuickはJUnit、CheckはJUnit・coverage・
benchmark・docs・frontend・wheel・sdist、Releaseはintegration JUnitとdesktop／
mobile画像、DeepはDeep JUnitを必須とします。コマンドが0終了しても必須成果物の欠落、
wheel／sdistの重複、run開始前から残る古い成果物があれば`artifact-validation`を
`error`にします。docsはCheckごとに既存出力を削除して再構築し、frontendは
`emptyOutDir`、packageは専用出力の削除後に再構築します。
CIは隠しディレクトリを明示的に許可し、`.werewolf-agent/quality`と
`.werewolf-agent/build`だけをartifactとして回収します。DB、運用log、QAは
CI artifactへ含めません。

`clean`は再生成可能なbuild、リポジトリ内とOS一時領域の品質tool cache、coverage、
保持期限を過ぎたrunだけを削除します。uvやnpmのpackage cache、DB、運用log、QA、最新run、`.venv`、
`node_modules`、`.env`は保持します。OneDriveのACLと競合するpytestの一時領域は
OSの一時ディレクトリを使い、保持するreportと成果物だけを`.werewolf-agent`へ置きます。
再生成可能なディレクトリの削除競合は、管理領域内に限定して短時間再試行します。
`latest.json`が欠落または破損している場合も、更新時刻が最も新しいrunを保護します。
負の保持日数、設定上限を超えるworker数、0以下のworker数とtimeoutは処理開始前に
拒否します。

## 制約

- 品質実行中に依存install、browser download、Docker build／pull、online auditを行いません。
  Supabase imageや事前構築済みE2E／runtime image不足時は取得せず`blocked`に
  します。browser、image、build cacheの取得は初回セットアップだけで行います。
- 一般の子processは外部向けHTTP/HTTPS proxyを到達不能なloopbackへ固定し、
  `NO_PROXY`はloopbackだけに限定します。pytestのsocket guardとPlaywright routingも
  localhost以外を拒否します。Playwrightは外部requestを遮断するだけでなく、試行した
  hostがあればテストを失敗させます。Chromiumの背景通信、同期、component更新確認も
  起動引数で無効化します。Streamlit E2Eが起動するworkerと画面processにも同じ環境を
  適用するため、品質runnerを経由しない明示的なpytest実行でも秘密情報を継承しません。
- Docker imageはrunner開始前に現行DockerfileとComposeから構築します。runnerは
  `--no-build`、`--pull never`、`--network none`の検査だけを行います。
- LLM providerは追加環境設定より後にFakeへ固定し、API keyやtokenを子processへ
  渡しません。外部通信防止設定も同じ順序で強制します。
- Python testとPlaywrightはlocalhost以外への接続を拒否します。一般の外部toolを
  OS firewallで遮断するものではないため、品質runnerが起動するcommand自体を固定します。
- telemetryを無効化し、reportとlogへ代表的なsecret値を残しません。
  E2Eの子process出力もrun固有の`logs/e2e`へ保存し、終了時に同じ規則で伏せ字化します。
  伏せ字処理はE2E専用領域に限定し、並列gateのlogには触れません。
- Supabase事前確認は`.env`と開発用DBを変更しません。品質専用のauth session、
  container、volume、project設定と`SUPABASE_HOME`はrunごとに隔離し、終了時に
  削除します。
- Supabase CLIは`2.104.0`に固定し、対応するimageを初回セットアップで取得します。
- timeoutやrunner割り込み時は子孫processを含めて停止します。release/deepでは
  preflight開始前に品質用projectの所有情報を確定し、Pythonの`finally`を実行できる
  異常経路でもlocal Supabaseを停止します。CIでも終了処理を重ねて実行します。
