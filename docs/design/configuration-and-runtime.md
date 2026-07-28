(configuration-runtime)=
# 設定と実行環境

環境ごとに変わる値は設定から解決し、ゲームルール、provider、database、ログ、
再試行をコードへ埋め込まない。設定は起動時に読み込み、矛盾を処理開始前に報告する。

## 設定源

`AppSettings`はpackaged TOML、リポジトリの`.env`、プロセス環境変数、明示引数の順に
値を上書きする。packaged TOMLを既定値の正本とする。composition rootが明示して渡す初期値は、
テストや限定された組み立てに使う。CLIのgame操作optionはrequest値であり、
application settingsの暗黙overrideとして扱わない。

設定fieldはAPI、worker、client、database、LLM、logging、gameのsection modelが
所有する。`AppSettings`はsectionを合成して環境変数を一度だけ解決するcomposition
modelであり、個別fieldを直接定義しない。sectionの一覧はarchitecture manifestを
正本とし、fieldの重複と未所属を構造テストで禁止する。applicationへは
`GameApplicationConfig`、LLMアダプターへは`LlmProviderConfig`へ縮小して渡す。

同じ値に複数の名前や暗黙fallbackを設けない。秘密値はversion管理する設定
ファイルへ置かず、環境変数または実行基盤から渡す。

packaged resourceは所有機能へ配置する。applicationは`resources/setups`のtemplateとcatalog、
agentsはprovider非依存prompt、LLMアダプターはFakeListChatModel fixture、Streamlit clientは
i18nとCSS、settingsはruntimeデフォルトを所有する。settingsはpathとruntime値だけを検証し、resourceの読込みと
定義間の相互参照検証はアダプターがcomposition時に行う。resourceはpackage APIから
読み、作業directoryに依存しない。

Streamlitのworkspace順序、tab、必須領域、column比は各viewの製品仕様とする。CSSは
`tokens`、`base`、`layout`、`components`、`streamlit`、`responsive`の固定順で読み、外部から
差し替えない。native widgetの色、文字、border、focusはリポジトリ管理の`.streamlit/config.toml`
を正とし、packaged CSSは固有表現とkey付きcontainerの配置だけを扱う。翻訳だけは運用上の
外部overrideを許可し、欠落または破損時は理由を構造化ログへ記録してpackaged catalogへ戻す。
rule、認証、秘匿設定にはfallbackを設けない。workspace順序は通常時と縮退時のnavigationで同じ
製品仕様を使う。表示密度は一つに固定し、分析領域はRecordsとAdminのexpanderで折りたたむ。

runtime statusはdatabaseとoperation queueを独立した読取probeで判定する。probe失敗はプロセスを
停止せず、各requestで状態を再評価して復旧を反映する。queueへの追加は可用性guardを通し、
queue障害時も既存operationの参照を維持する。

## 実行プロセス

| プロセス | 入口 | 主な責務 |
| --- | --- | --- |
| API | `werewolf-agent-api` | HTTP、認証、application composition |
| worker | `werewolf-agent-worker` | operation queue、自動進行、LLM |
| CLI | `werewolf-agent` | 診断とHTTP client操作 |
| Streamlit | `streamlit run .../app.py` | ブラウザーUI |

起動はconsole entrypoint、VS Code task、Docker Composeのいずれでも同じ設定モデルを
使う。起動手段ごとの設定コピーを作らない。

APIとworkerのpool size、取得timeout、workerのvisibility timeout、heartbeat、最大試行回数は
同じ設定modelで検証する。instance IDはAPIプロセスの識別だけに使う。

## ログと観測

実行contextにrequest、game、operationの識別子を保持し、外部境界で構造化ログを記録する。
常駐プロセスのログは`.werewolf-agent/logs/application`で機能別fileに分ける。有限の環境操作、
品質確認、レビューはログdirectoryへ混在させず、run単位のreportとmanifestを所有する。

`@timestamp`、`log.level`、`service.name`、`service.version`、`event.action`、
`event.outcome`、`event.duration`、`trace.id`、`operation.id`、`error.code`、`error.type`、
`error.message`を安定fieldとし、秘密情報をredactionしてからsinkへ渡す。ERRORは最終失敗、WARNINGは縮退と
retry、INFOは重要な状態変化、DEBUGはpolling、rerun、health成功、判定過程に使用する。
stack traceはERRORだけへ付与する。domainとapplicationはlogging設定に依存しない。

local fileは10 MiBでrotateし、backupを3世代保持する。Composeとproductionはstdoutを使用し、
長期保持、検索、通知は外部運用基盤が担当する。file名はプロセス入口が所有し、API、worker、
CLI、Streamlitを同じfileへ集約する設定は公開しない。

operationはkindごとに10件、合計50 MiB、レビューはkindごとに3件、合計100 MiBを上限とする。
privateレビュー evidenceは7日で削除し、active markerを持つrunは削除しない。保持値は
`pyproject.toml`の`tool.werewolf-artifacts`を正本とする。

## 実行前検証

設定診断が必須設定、resource、接続先の構成を検査する。外部接続を
必要とする検証は明示したpreflightに分け、通常のunitテストと品質runnerが
外部APIを暗黙に呼ばないようにする。
