# Streamlit UI

Streamlit 画面の検討メモです。実装の正は A案をベースにした Play / Observe 共通設定画面です。
右側にプレイヤー状態を再掲せず、中央の `ゲーム卓` に集約します。右側は Play では `あなたの手番`、
Observe では `観戦ログ` を主役にします。

この画面では後方互換を維持しません。旧 UI、旧保存形式、旧 session state、旧入力導線へ
合わせる処理は作らず、現在の UX と保守性を優先します。

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

- メイン初期画面: `ゲーム開始設定`。初回表示と sidebar の `プレイ` は常に開始設定へ戻す
- 左サイドバー: `API 接続`、`保存データ`、`プレイ`、`観戦`、`設定`
- `保存データ`: プルダウンから保存スロットを選び、game ID や操作用キーは画面に出さない
- `ゲーム開始設定` / `観戦開始設定`: 役職ごとの人数を `+/-` 相当の number input で設定し、全体人数の直接入力は置かない
- `設定`: 言語と local rules を編集する詳細設定画面。開始設定内には詳細設定 popup を置かない
- 上部ステータス: フェーズ、日数、生存人数、経過ターン、現在の手番、状態、勝敗
- 中央: `ゲーム卓`
- 右側: Play では `あなたの手番`、`あなたの役職`、`見えている情報`、`できる行動`
- 右側: Observe では操作 UI を出さず、全役職と投票・夜行動の reveal 情報を `観戦ログ` にまとめる
- 中央下: `公開タイムライン`。completed 時は末尾に `結果サマリー` と次の選択を表示する

mobile では `ゲーム卓`、右ペイン相当、`公開タイムライン` の順で縦積みします。

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
- UI 文言とイベント種別、行動、フェーズ、役職の表示名は `resources/streamlit/i18n.toml` に閉じる
- `WEREWOLF_STREAMLIT_I18N_FILE` を指定すると外部 TOML で UI 文言を差し替えられる
- 画面起動時の初期言語は `WEREWOLF_STREAMLIT_LANGUAGE` を使い、実行中の選択は Streamlit session state に保持する
- `streamlit/icons.py` は icon metadata だけを持ち、label は i18n catalog から取得する
- 後からログアイコンや専用画像に置き換える場合も、画面本体ではなくマップを差し替える
- `app.py` は Streamlit widget と画面配置だけを担当する
- API 呼び出しは `streamlit/operations.py` から `GameApiClient` protocol を直接使う
- 発言・投票送信後は公開 API の `/advance` を 1 回だけ呼び、次の手番へ進める
- `入力待ちまで進める` は Streamlit session state と `st.fragment` で 1 step ずつ進め、`一時停止` で次 step 前に止める
- 右ペインは `right_command_panel` container を操作盤の外枠とし、手番状態、秘匿観測、操作、観測メモを固定順に並べる
- domain / usecase の `available_actions` を正とし、画面側だけで多重発言や多重投票を隠す実装にはしない
- HTML 断片と escape は `streamlit/components.py` に閉じ、`app.py` に重複させない
- `view_models.py` は表示用データ変換だけを担当し、Streamlit、domain、usecase、`interface/shared` に依存させない
- `公開タイムライン` には `/timeline` の `GameTimelineItem` だけを使う
- 右ペイン最下部の `観測メモ（公開情報）` は public state と public timeline だけから作り、private observation や reveal は混ぜない
- 発言内容、投票、投票結果、夜明けの犠牲者有無は表示し、夜行動の対象、護衛先、占い結果、role は表示しない
- Observe は `GET /api/v1/games/{game_id}/reveal` だけから秘匿情報を読み、Play の表示 model へは混ぜない
- 操作用キーは `.werewolf-agent/streamlit/saves.json` の新形式保存スロットに閉じ、画面やログには出さない
- seed、発言文字数、作成時ルールは `AppSettings` から読む

## ブラウザ QA

Browser plugin は直接 tool として見えない場合でも、`node_repl` から初期化できます。
desktop / mobile の再検証手順は [streamlit-browser-qa.md](streamlit-browser-qa.md) に残します。
