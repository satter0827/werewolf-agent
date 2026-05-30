# Streamlit UI

Streamlit 画面の検討メモです。実装の正は A案です。右側にプレイヤー状態を再掲せず、
中央の `ゲーム卓` に集約します。右側は `あなたの手番` だけを主役にします。

## 目的

- 一般ユーザーが Streamlit だけで 1 game を開始し、1 human player として決着まで遊べる
- 画面は FastAPI の公開 HTTP API だけを使い、domain / usecase / DB へ直接触れない
- 文言はゲームらしさと分かりやすさのバランスを取り、メタ表現を画面本文に出さない
- 設定値、表示モデル、API 操作、HTML 部品を分け、画面変更が内側の層へ波及しないようにする

## 採用案

![A案: バランス型](assets/streamlit-ui/02-playable-balanced.png)

A案を実装の基準にします。中央の `ゲーム卓` にプレイヤー状態を集約し、右側は `あなたの手番` と
行動入力に集中させます。プレイヤー一覧と生存状態は右側に再掲しません。

画面構成:

- 左サイドバー: `API 接続`、`現在のゲーム`、`新しいゲーム`
- `現在のゲーム`: 選択中 game、最近の game、game ID 指定、操作するプレイヤー、操作用キーを統合
- 上部ステータス: フェーズ、日数、生存人数、経過ターン、現在の手番、状態、勝敗
- 中央: `ゲーム卓`
- 右側: `あなたの手番`、`あなたの役職`、`見えている情報`、`できる行動`
- 中央下: `これまでの流れ`

mobile では `ゲーム卓`、`あなたの手番`、`これまでの流れ` の順で縦積みします。

## 比較案

![参照: story timeline](assets/streamlit-ui/01-reference-story-timeline.png)

![B案: チャット型](assets/streamlit-ui/03-playable-chat.png)

![C案: ガイド型](assets/streamlit-ui/04-playable-guided.png)

## QA 画像

`.werewolf-agent/cache` は一時キャッシュです。画面検討・QA の画像は docs 配下へ置きます。

- ![QA desktop console](assets/streamlit-ui/07-qa-console-desktop.png)
- ![QA observer desktop](assets/streamlit-ui/08-qa-observer-desktop.png)
- ![QA observer mobile](assets/streamlit-ui/09-qa-observer-mobile.png)
- ![QA zero-base review](assets/streamlit-ui/10-qa-zero-base-review.png)

## 実装メモ

- アイコンは当面、Streamlit 標準で扱える絵文字/記号を使う
- イベント種別、行動、フェーズ、役職の表示名は `streamlit/icons.py` のマップに閉じる
- 後からログアイコンや専用画像に置き換える場合も、画面本体ではなくマップを差し替える
- `app.py` は Streamlit widget と画面配置だけを担当する
- API 呼び出しは `streamlit/operations.py` から `interface/shared.workflows` を使う
- HTML 断片と escape は `streamlit/components.py` に閉じ、`app.py` に重複させない
- `view_models.py` は表示用データ変換だけを担当し、Streamlit、domain、usecase、`interface/shared` に依存させない
- `これまでの流れ` には `/turns` の公開 read model だけを使う
- 操作用キーは `st.session_state` と password input に閉じ、永続保存しない
- seed、発言文字数、作成時ルールは `AppSettings` から読む

## ブラウザ QA

Browser plugin は直接 tool として見えない場合でも、`node_repl` から初期化できます。
desktop / mobile の再検証手順は [streamlit-browser-qa.md](streamlit-browser-qa.md) に残します。