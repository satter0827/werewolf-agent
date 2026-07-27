(configuration-runtime)=
# 設定と実行環境

環境ごとに変わる値は設定から解決し、ゲームルール、provider、database、ログ、
再試行をコードへ埋め込まない。設定は起動時に読み込み、矛盾を処理開始前に報告する。

## 設定源

`AppSettings` はpackaged TOML、repositoryの`.env`、process環境変数、明示引数の順に
値を上書きする。packaged TOMLを既定値の正本とする。composition root が明示して渡す初期値は、
テストや限定された組み立てに使う。CLI の game 操作 option は request 値であり、
application settings の暗黙 override として扱わない。

設定fieldはAPI、worker、client、database、LLM、logging、gameのsection modelが
所有する。`AppSettings`はsectionを合成して環境変数を一度だけ解決するcomposition
modelであり、個別fieldを直接定義しない。sectionの一覧はarchitecture manifestを
正本とし、fieldの重複と未所属を構造テストで禁止する。applicationとagentsへは
applicationへは`GameApplicationConfig`、LLM adapterへは`LlmProviderConfig`へ縮小して渡す。

同じ値に複数の名前や暗黙 fallback を設けない。秘密値は version 管理する設定
ファイルへ置かず、環境変数または実行基盤から渡す。

packaged resourceは所有機能へ配置する。applicationはゲーム定義、agentsはpromptと
FakeListLLM fixture、Streamlit clientはi18nとCSS、settingsはruntime
defaultを所有する。settingsはpathとruntime値だけを検証し、resourceの読込みと
定義間の相互参照検証はadapterがcomposition時に行う。resourceはpackage APIから
読み、作業directoryに依存しない。

Streamlitのworkspace順序、tab、必須領域、column比は各viewの製品仕様とする。CSSは
`tokens`、`base`、`layout`、`components`、`streamlit`、`responsive`の固定順で読み、外部から
差し替えない。native widgetの色、文字、border、focusはrepository管理の`.streamlit/config.toml`
を正とし、packaged CSSは固有表現とkey付きcontainerの配置だけを扱う。翻訳だけは運用上の
外部overrideを許可し、欠落または破損時は理由を構造化logへ記録してpackaged catalogへ戻す。
rule、認証、秘匿設定にはfallbackを設けない。workspace順序は通常時と縮退時のnavigationで同じ
製品仕様を使う。表示密度は一つに固定し、分析領域はRecordsとAdminのexpanderで折りたたむ。

runtime statusはdatabaseとoperation queueを独立した読取probeで判定する。probe失敗はprocessを
停止せず、各requestで状態を再評価して復旧を反映する。queueへの追加は可用性guardを通し、
queue障害時も既存operationの参照を維持する。

## 実行プロセス

| プロセス | 入口 | 主な責務 |
| --- | --- | --- |
| API | `werewolf-agent-api` | HTTP、認証、application composition |
| worker | `werewolf-agent-worker` | operation queue、自動進行、LLM |
| CLI | `werewolf-agent` | 診断と HTTP client 操作 |
| Streamlit | `streamlit run .../app.py` | 補助 UI |
| React | frontend package scripts | 本番 browser UI |

起動は console entrypoint、VS Code task、Docker Compose のいずれでも同じ設定モデルを
使う。起動手段ごとの設定コピーを作らない。

APIとworkerのpool size、取得timeout、workerのvisibility timeout、heartbeat、最大試行回数は
同じ設定modelで検証する。`WEREWOLF_API_INSTANCE_ID`はAPI processの識別だけに使う。

## ログと観測

実行 context に request、game、operation の識別子を保持し、外部境界で構造化ログを
記録する。ログファイルは `worker.jsonl`、`streamlit.jsonl`、`cli.jsonl` のように
機能名で分ける。起動ツールや作業者の名前を含めない。

時刻、level、event、context、error code を安定した field とし、秘密情報を
redactionしてからsinkへ渡す。domainとapplicationはlogging設定に依存しない。

## 実行前検証

`werewolf-agent system doctor` が必須設定、resource、接続先の構成を検査する。外部接続を
必要とする検証は明示した preflight に分け、通常の unit test と品質 runner が
外部 API を暗黙に呼ばないようにする。
