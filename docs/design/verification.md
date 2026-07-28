(verification)=
# 検証

## 対象と責務

品質基盤は、リポジトリ内のソースコード、テスト、fixture、ローカルプロセス、Compose
serviceから製品の合否を判定する。package取得先や有料providerの可用性は、製品品質と
区別して扱う。

## 品質プロファイル

| プロファイル | 責務 |
| --- | --- |
| `auto` | 変更pathを責務境界へ対応付け、必要なプロファイルまたは部分gateを選ぶ |
| `focus` | architecture、format、lint、型、unit、軽量statefulを検査する |
| `check` | Focus、coverage、offline integration、docs、OpenAPI、Schemathesis、buildを検査する |
| `release` | Check、Supabase、API、worker、clients、ブラウザー、package、containerを検査する |
| `deep` | 長時間stateful、fault injection、性能を観測する |
| `review` | UI、Gameplay、Local LLMの読解用証拠を生成する。合否には含めない |

`auto`の変更pathと選定結果の対応は`scripts/quality/impact.toml`を正本とする。具体的な
実行コマンド、`--fresh`、個別gate、環境準備は`scripts/README.md`が所有する。

## 外部接続境界

品質プロセスからprovider credentialと外部base URLを除去し、fake providerとtelemetryの
無効化を強制する。Pythonテスト、Playwright、E2E containerは非loopback通信を拒否する。
依存取得は`scripts.environment`へ分離し、品質プロファイルは実行中に依存環境を変更しない。

利用者は運用設定として有料providerを選択できる。ただし、そのcredential、応答、可用性を
品質判定やレビューの前提にしない。Local LLMレビューはloopbackだけを許可する。

## 判定

- `passed`: 検査を満たす。
- `failed`: assertion、lint、型、契約に違反する。
- `blocked`: tool、権限、Docker、ローカルserviceなどの実行条件が不足する。
- `error`: runnerまたは検査基盤が異常終了する。
- `skipped`: 依存gateが完了していない。

## 検証境界

architectureテストは`scripts/architecture/rules.toml`を正本とし、import graphから間接依存、
循環、公開面を検査する。OpenAPI operation、`FeatureSpec`、CLIコマンド、Streamlit workspaceを
照合し、配置だけが存在する未実装を許可しない。

domainテストは状態遷移、復元snapshot、役職構成、終局結果、pending actionの参照整合を
検証する。リプレイテストはコマンド、event、state、projection、rule snapshotの改変を最初の
不一致versionで検出する。

client faultテストはAPI、Auth、database、operation queue、worker、LLM、翻訳overrideを個別に
故障させ、停止範囲が依存するfeatureに限られることを確認する。環境準備テストはfingerprint、
Docker、image、隔離Supabase projectを独立して検証する。

coverage、benchmark、ゲームバランス、会話品質には、根拠のない合否閾値を設けない。観測値と
読解用証拠の契約は、{ref}`evidence-diagnostics`で定義する。
