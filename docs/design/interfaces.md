(interfaces)=
# 利用者インターフェース

React、CLI、Streamlit は同じ HTTP API を通じてゲームを操作する。各画面は表示と
入力に集中し、ゲームルールや公開範囲を再実装しない。

## React

React は本番利用者向け UI である。ゲーム通信には OpenAPI から生成した client を
使い、Supabase client は Auth だけに使う。画面状態は server response から導出し、
合法手、フェーズ遷移、勝敗を browser 内で再計算しない。

browser E2E はログイン、game 作成、操作、更新、エラー表示の主要導線を検証する。
selector は見た目の階層ではなく role と利用者向けラベルを優先する。

## CLI

CLI は自動化、診断、開発確認の入口である。console entrypoint を使い、HTTP
`GameClient` を通して操作する。machine-readable な出力を選べるコマンドでは、
標準出力へ安定した schema を返し、診断ログと分離する。

## Streamlit

Streamlit は操作確認と可視化の補助 UI である。session state には画面上の選択だけを
保持し、完全な domain state や repository を埋め込まない。再実行時も API response
を基準に表示 model を再構築する。

## 共通境界

- 内部例外と stack trace を利用者へ表示しない。
- error code を画面固有の文言へ変換し、同じ意味の文言を共通化する。
- 通常 client に private state を送ってから隠す設計にしない。
- 管理者 reveal を通常の `GameClient` と画面導線へ追加しない。
- 起動手段に依存する分岐を application code へ入れない。
