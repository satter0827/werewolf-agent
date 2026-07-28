# ゲーム設定

## 正本

ゲーム作成の正本は`GameSetupDocument v2`である。documentは次の領域を必須で持つ。

- `mechanics`: 役職数、任意IDの役職、能力component、共通ルール
- `theme`: 世界観、導入、用語、説明、ナレーション
- `player_generation`: identity、公開persona、非公開strategyの候補

同梱template、保存revision、inline documentはAPI受付時に完全なdocumentへ解決する。同じ時点で
seedとプレイヤーを確定し、setup、mechanics、rosterのchecksumを含む正規化済みコマンドをqueueへ
保存する。workerはtemplateや保存revisionを再解釈しない。

同梱templateと一覧catalogは`src/werewolf_agent/application/resources/setups`、runtimeの
既定template IDは`src/werewolf_agent/settings/resources/defaults.toml`を正本とする。
外部file overrideのpathはsettingsが検証し、documentの読込みと相互参照はapplication側の
setup loaderが検証する。

## 固定境界と可変要素

phaseの基本構造、公開・秘匿境界、event保存、agent protocol、`village`、`werewolf`、`fox`の
勝敗判定はコードが所有する。役職ID、役職数、能力の組み合わせ、対象条件、開始日、使用回数、
解決優先度、共通ルール、表示、プレイヤー生成候補は設定が所有する。

役職は`identity_faction`、`victory_team`、能力IDの集合だけを持つ。能力componentは`attack`、
`inspect`、`protect`、`eliminate`、`knowledge`、`death_reaction`、`immunity`、
`vulnerability`に限定する。外部コード、import path、汎用DSLは受け付けない。

受動能力は実行系が意味を持つ組み合わせだけを受け付ける。`immunity`は夜の`attack`、
`eliminate`、`inspect`、`vulnerability`は夜の`inspect`を発生元にできる。
`death_reaction`は夜または投票で解決する。発生しないphaseや未対応の発生元は設定検証で拒否する。

行動は`speech`、`vote`、`use_ability`、`pass`へ統一する。`use_ability`は能力IDを必須とし、
合法対象、agent decision、HTTP action、復元、replayまで同じenvelopeを使用する。

## プレイヤー生成

ゲームごとに`p1`から始まるseatを生成する。identityは重複なしで抽選し、公開personaと非公開strategyは
seed付きshuffleと巡回割当で分散する。identity不足、空の候補集合、重複名は設定エラーにする。

ゲームseedから`roster`、`role_assignment`、`gameplay`のseedをSHA-256で分離する。同じdocumentと
seedは同じプレイヤー、役職割当、ゲーム進行を再現する。previewはseat、名前、年齢、性別表現、性格、
話し方だけを返し、役職と非公開strategyを返さない。

## themeと秘匿性

themeは選択中の役職、能力、陣営、行動、phaseを漏れなく命名する。表示用の語彙をdomainの安定IDと
分離し、公開状態、timeline、画面、LLM contextへ同じ表現を渡す。

ナレーションを有効にする場合は、対応する公開eventをすべて定義する。templateは公開済みの値だけを
差し込み可能とし、未対応event、未知の差し込み項目、壊れたformatは設定検証で拒否する。

公開状態とtimelineへ生存者の役職、未解決の投票、夜の行動、調査結果、非公開strategyを含めない。
LLMには本人の役職、本人のプロファイル、観測から判明した情報、本人に関係する設定だけを渡す。

## 保存revision

利用者の設定は`private.user_setups`と`private.user_setup_revisions`へ保存する。revisionは追加専用で、
保存時に親行をlockし、`expected_revision`と最新revisionが一致する場合だけ次版を追加する。競合は
HTTP 409とする。

リポジトリの全取得は所有者IDで絞る。他利用者の設定は404、匿名利用者の保存とrevision参照は403に
する。private tableはData APIへ公開せず、`anon`と`authenticated`へ直接権限を付与しない。

## 利用者導線

Streamlitの「ゲーム設定」は「世界観」「役職と能力」「プレイヤー生成」「ルール」「確認」を編集する。
同梱templateの編集は保存設定への複製として開始し、保存済み設定は「新しい版として保存」でrevisionを
追加する。匿名利用者も編集中のinline documentをpreviewとゲーム作成に使用できる。

ゲーム作成画面は設定、revision、再現用の番号、プレイヤー preview、手動seat、agentの熟考度、最終確認だけを
扱う。設定または番号が変わった場合は古いpreviewを使用しない。

CLIは`setup show`、`setup export`、`setup validate`、`setup inspect`と
`game create --setup-file`を提供し、HTTP APIと同じ検証境界を使用する。
