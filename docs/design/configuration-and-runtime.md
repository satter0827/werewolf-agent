(configuration-runtime)=
# 設定と実行環境

環境ごとに変わる値は設定から解決し、ゲームルール、provider、database、ログ、
再試行をコードへ埋め込まない。設定は起動時に読み込み、矛盾を処理開始前に報告する。

## 設定源

`AppSettings` は packaged default を基準にし、repository の `.env` と process
環境変数から実行環境の値を解決する。composition root が明示して渡す初期値は、
テストや限定された組み立てに使う。CLI の game 操作 option は request 値であり、
application settings の暗黙 override として扱わない。

設定fieldはAPI、worker、client、database、LLM、logging、gameのsection modelが
所有する。`AppSettings`はsectionを合成して環境変数を一度だけ解決するcomposition
modelであり、個別fieldを直接定義しない。sectionの一覧はarchitecture manifestを
正本とし、fieldの重複と未所属を構造テストで禁止する。applicationとagentsへは
`GameApplicationConfig`と`LlmProviderConfig`へ縮小して渡す。

同じ値に複数の名前や暗黙 fallback を設けない。秘密値は version 管理する設定
ファイルへ置かず、環境変数または実行基盤から渡す。

packaged resourceは所有機能へ配置する。applicationはゲーム定義、agentsはpromptと
FakeListLLM fixture、Streamlit clientはi18n、CSS、screen定義、settingsはruntime
defaultを所有する。settingsはpathとruntime値だけを検証し、resourceの読込みと
定義間の相互参照検証はadapterがcomposition時に行う。resourceはpackage APIから
読み、作業directoryに依存しない。

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

## ログと観測

実行 context に request、game、operation の識別子を保持し、外部境界で構造化ログを
記録する。ログファイルは `worker.jsonl`、`streamlit.jsonl`、`cli.jsonl` のように
機能名で分ける。起動ツールや作業者の名前を含めない。

時刻、level、event、context、error code を安定した field とし、秘密情報を
redactionしてからsinkへ渡す。domainとapplicationはlogging設定に依存しない。

## 実行前検証

`werewolf-agent doctor` が必須設定、resource、接続先の構成を検査する。外部接続を
必要とする検証は明示した preflight に分け、通常の unit test と品質 runner が
外部 API を暗黙に呼ばないようにする。
