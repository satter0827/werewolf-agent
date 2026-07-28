(clients)=
# 利用者クライアント

CLIとStreamlitは同じHTTP APIを通じてゲームを操作する。各画面は表示と
入力に集中し、ゲームルールや公開範囲を再実装しない。

## CLI

CLIは自動化、診断、開発確認の入口である。`system`、`setup`、`game`、`records`、
`admin`の利用目的でコマンドを分ける。公開情報は`PublicClient`、通常操作は
`GameClient`、管理操作は`AdminClient`を通す。machine-readableな出力を選べるコマンドでは、
標準出力へ安定したschemaを返し、診断ログと分離する。

## Streamlit

Streamlitは唯一のブラウザーUIであり、状況確認と操作を一続きに扱うゲーム卓である。session stateには画面上の選択だけを
保持し、完全なdomain stateやリポジトリを埋め込まない。再実行時もAPI response
を基準に表示modelを再構築する。

表示modelは型、game state、timeline、observation/actionのモジュールに分ける。screenは
必要なprojectionだけをimportし、HTTP responseの変換をscreen本体へ重複させない。

workspaceは`Play`、`Observe`、`Records`、`Admin`、`Preferences`の順に扱う。順序、tab、
必須領域、列構造は各viewが製品仕様として所有し、外部定義で変更しない。管理者と確認できない
場合は`Admin`を表示しない。認証や保存機能を利用できない場合も表示設定、navigation、現在可能な
操作と復旧方法を描画し、guestや管理者へ暗黙昇格しない。ゲーム情報を分析情報より先に置き、分析
領域は初期状態で折りたたむ。ゲーム画面はstatus ribbon、単一のtableau、native widgetの操作rail、
公開timelineの順に描画する。独自HTMLはstatus ribbon、tableau、timelineだけに限定する。
`Records`は公開stateと解決済みtimelineを取得し、
物語としてのreplayと分析を同じ記録導線で分けて表示する。

databaseが利用できない場合は権威あるstateを表示しない。operation queueだけが利用できない
場合はstate、timeline、記録の参照を維持し、作成、行動、進行だけを停止する。表示するerrorは
安定したerror codeから利用者向けの状態と復旧方法へ変換し、内部アダプターの文言を直接表示しない。

workspaceを切り替えた場合だけmain領域を先頭へ戻す。自動更新と同じworkspace内の操作では
scrollと入力focusを維持し、利用者の読解や入力を中断しない。

`FeatureSpec`はOpenAPI operation ID、利用者区分、依存先、client配置を対応付ける。CLIの
登録コマンドとStreamlit rendererは実装するFeature IDを宣言する。OpenAPI、CLIコマンド、
Streamlit workspace、renderer宣言の未知参照、未配置、重複を構造テストで検出する。

### 表示とaccessibility

desktopはゲーム情報、tableau、操作、公開timelineの階層を明確にし、mobileは同じDOM順で
一列へ積む。狭幅でhorizontal overflowを発生させず、主要操作、keyboard focus、heading順、
入力label、状態通知、contrastをブラウザーE2Eで確認する。完了時は結果をtimelineより前に示し、
不要になった進行操作を表示しない。

一般画面にはAPI、database、queueなどの内部構成や例外詳細を出さず、現在利用できる機能と
復旧方法を表示する。現行画面の証拠は品質runのブラウザー成果物を正本とし、設計書へ画像を固定しない。

## 共通境界

- 内部例外とstack traceを利用者へ表示しない。
- error codeを画面固有の文言へ変換し、同じ意味の文言を共通化する。
- 通常clientにprivate stateを送ってから隠す設計にしない。
- 管理者revealを通常の`GameClient`と画面導線へ追加しない。
- 起動手段に依存する分岐をapplication codeへ入れない。
