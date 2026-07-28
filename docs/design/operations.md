(operations)=
# 運用

リポジトリ内では起動前検証、migration、worker実行、品質確認、調査用成果物の生成を
コード化する。配置、backup、監視通知、権限管理は外部運用基盤の責務とし、その入力と
確認条件をapplicationの設定とhealth signalに接続する。

## 起動

1. 実行基盤がrevision、設定、credentialを配置する。
2. migration jobがschemaを確認して必要なmigrationを適用する。
3. APIとworkerが設定とpackaged resourceを検証して起動する。
4. `/health`の`instance_id`、`started_at`、`config_fingerprint`が対象プロセスを確認する。
5. Streamlitが対応するAPI contractを使って公開される。

各プロセスと`doctor`は同じ`AppSettings`とresource loaderを使う。VS Code、
Docker、配布基盤で別の設定validationを作らない。

`/health`はinstanceを識別できるliveness signalであり、databaseやqueueのreadinessを
保証しない。E2Eは起動時に発行したinstance IDとの一致を確認してから操作する。
schemaと接続の確認はmigrationと環境別preflightが担当する。外部運用基盤は
liveness、migration結果、workerのoperation signalを別々に監視する。

## 定常運用

API request、worker operation、LLM provider callをcorrelation IDで追跡する。
error code、latency、queue滞留、再試行、provider使用量を外部監視基盤へ渡す。
ログ本文にprivate stateとcredentialを含めない。

workerは待機時間が正の場合だけ`read_with_poll`、0の場合は非pollingの`read`で設定件数を
取得する。中断はPGMQ visibility timeout後の再配送で
回復し、`read_ct`をledgerの`attempt_count`へ同期する。heartbeat、完了、再試行は
`queue_message_id`、`worker_id`、`attempt_count`の一致で所有権を確認する。retryable errorは
messageをarchiveせず再配送し、検証失敗、重複message、最大試行回数超過は業務処理を
繰り返さずsafe Problem Detailsとともに`failed`またはarchiveへ確定する。

## 問題調査

1. `scripts/README.md`の診断入口から成果物の参照viewを生成する。
2. error code、run ID、trace ID、operation IDから対象reportとログを特定する。
3. 観測事実、確定原因、仮説、未確認範囲を分離して失敗境界を絞る。
4. 同じ設定とfixtureで再現テストを作る。
5. 修正後に対象テストと品質プロファイルを実行する。

diagnosticsはapplicationログ、operation、quality、レビューを複製せず、pathとhashで参照する。
manifestが存在するreportはSHA-256を照合し、不一致を成果物破損として扱う。
`report.json`を機械判定、`summary.md`を人間の初動調査に使用する。確定原因には直接検査した
事実だけを記録し、subprocessの失敗だけから根本原因を推測しない。

品質成果物の分類、参照先、保持契約は{ref}`evidence-diagnostics`を正本とする。固定したテスト件数や
過去の画面画像を運用判断へ使用しない。

品質用Composeは固定project名と所有labelで一組だけ起動し、一時jobへ`--rm`を指定する。
runnerは開始前後の子プロセスと所有resourceを比較し、終了待機後も残る場合は異常とする。
利用者が起動した無関係なcontainer、volume、プロセスはcleanup対象にしない。

## 外部運用境界

本番のdeployment、database backupとrestore、monitoring rule、on-call通知、
credential rotationは配布基盤で管理する。リポジトリはhealth endpoint、構造化
signal、migrationコマンド、設定契約を提供し、外部基盤固有の手順をapplication
codeへ埋め込まない。
