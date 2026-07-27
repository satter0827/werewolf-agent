(operations)=
# 運用

repository 内では起動前検証、migration、worker 実行、品質確認、調査用成果物の生成を
コード化する。配置、backup、監視通知、権限管理は外部運用基盤の責務とし、その入力と
確認条件を application の設定と health signal に接続する。

## 起動

1. 実行基盤が revision、設定、credential を配置する。
2. migration job が schema を確認して必要な migration を適用する。
3. API と worker が設定と packaged resource を検証して起動する。
4. `/health` の`instance_id`、`started_at`、`config_fingerprint`が対象processを確認する。
5. Streamlitが対応するAPI contractを使って公開される。

各 process と `doctor` は同じ `AppSettings` と resource loader を使う。VS Code、
Docker、配布基盤で別の設定 validation を作らない。

`/health` はinstanceを識別できるliveness signalであり、databaseやqueueのreadinessを
保証しない。E2Eは起動時に発行したinstance IDとの一致を確認してから操作する。
schema と接続の確認は migration と環境別 preflight が担当する。外部運用基盤は
liveness、migration 結果、worker の operation signal を別々に監視する。

## 定常運用

API request、worker operation、LLM provider call を correlation ID で追跡する。
error code、latency、queue 滞留、再試行、provider 使用量を外部監視基盤へ渡す。
ログ本文に private state と credential を含めない。

workerは待機時間が正の場合だけ`read_with_poll`、0の場合は非pollingの`read`で設定件数を
取得する。中断はPGMQ visibility timeout後の再配送で
回復し、`read_ct`をledgerの`attempt_count`へ同期する。heartbeat、完了、再試行は
`queue_message_id`、`worker_id`、`attempt_count`の一致で所有権を確認する。retryable errorは
messageをarchiveせず再配送し、検証失敗、重複message、最大試行回数超過は業務処理を
繰り返さずsafe Problem Detailsとともに`failed`またはarchiveへ確定する。

## 問題調査

1. `python -m scripts.diagnostics collect`で最新成果物の参照viewを生成する。
2. error code、run ID、trace ID、operation IDから対象reportとlogを特定する。
3. 観測事実、確定原因、仮説、未確認範囲を分離して失敗境界を絞る。
4. 同じ設定とfixtureで再現testを作る。
5. 修正後に対象testと品質profileを実行する。

diagnosticsはapplication log、operation、quality、reviewを複製せず、pathとhashで参照する。
manifestが存在するreportはSHA-256を照合し、不一致を成果物破損として扱う。
`report.json`を機械判定、`summary.md`を人間の初動調査に使用する。確定原因には直接検査した
事実だけを記録し、subprocessの失敗だけから根本原因を推測しない。

品質reportの最新試行は`.werewolf-agent/quality/profiles/<profile>/current`、最終成功は
同じprofileの`last-passed.json`から解決する。固定したtest件数や過去の画面画像を運用判断へ
使用しない。BrowserとAgent reviewの成果物は`.werewolf-agent/reviews`に分離する。

品質用Composeは固定project名と所有labelで一組だけ起動し、一時jobへ`--rm`を指定する。
runnerは開始前後の子processと所有resourceを比較し、終了待機後も残る場合は異常とする。
利用者が起動した無関係なcontainer、volume、processはcleanup対象にしない。

## 外部運用境界

本番の deployment、database backup と restore、monitoring rule、on-call 通知、
credential rotation は配布基盤で管理する。repository は health endpoint、構造化
signal、migration command、設定契約を提供し、外部基盤固有の手順を application
code へ埋め込まない。
