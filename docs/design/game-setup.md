# ゲーム設定

## 正本

ゲーム作成の正本は`GameSetupDocument`である。presetもcustom設定もworkerで同じdocumentへ
解決し、domain設定、保存snapshot、replay、LLM contextはこのdocumentから生成する。
乱数seed、manual player、LLM providerの選択は実行条件であり、setupには含めない。

documentは次の3領域を持つ。

- `mechanics`: 役職数、役職、能力、ローカルルール、policy composition
- `theme`: 背景、導入、役職・陣営・能力・行動・phaseの表示名、narration
- `roster`: 登場人物とseatへの固定割当

`schema_version`、`setup_checksum`、`mechanics_checksum`を保存する。異なるversionの旧ゲームは
暗黙変換せず、新しいゲームの作成を案内する。

## mechanicsと表現の境界

domainは`werewolf`や`seer`などの安定IDだけを扱う。宇宙船では`werewolf`を「擬態生命体」、
江戸では「妖怪」と表示できるが、勝敗や能力は変わらない。themeは選択中の役職、能力、陣営、
行動、phaseをすべて命名し、役職の目的も背景固有の文章で定義しなければならない。この完全性は
setup validationで固定する。

ナレーション方式はゲームごとに`standard`または`none`を選び、作成requestと保存snapshotへ
記録する。`standard`の文章はtheme内のnarration templateから生成する。語り口の差はthemeが
所有し、同じ出力になる別名のmodeは設けない。

役職は`identity_faction`と`victory_team`を分離する。狂人は村側として判定され、人狼側の
勝利に参加する。妖狐は独立した勝利陣営で、襲撃耐性と調査弱点を持つ。

## ルールと能力

利用者が選ぶルールは挙動を表す値であり、内部policy IDを画面へ出さない。同票処理、襲撃同票、
占い・霊媒の情報粒度、開始phase、自己対象、再選択、初夜襲撃、死亡時公開を編集できる。

能力はphase、action、effect、対象条件、開始日、使用上限、結果公開範囲、解決優先度を持つ。
標準能力は襲撃、調査、護衛、霊媒、治療、毒、死亡時反撃、襲撃耐性、調査弱点である。
治療と毒はそれぞれ一度だけ使え、同じplayerは一夜に一行動だけ選ぶ。猟師の反撃は死亡時に
生存者からseedに基づいて自動解決し、連鎖も同じ規則で解決する。

## LLM context

LLMにはTOML全文や他playerのprivate情報を渡さない。`AgentGameContext`として背景の導入、
本人のtheme上の役職名、identity faction名、victory team名、背景固有の目的、利用可能な能力と残り回数、
現在の判断に関係するルール、theme上のaction・phase名を渡す。traceにはprompt version、
setup checksum、mechanics checksum、observation checksumを記録する。

この分離により、背景変更による語彙の一貫性と、mechanics変更による挙動差を別々に追跡できる。

## 利用者導線

Streamlitは「世界観」「役職」「登場人物」「ルール」の4段階で設定する。presetを起点に編集し、
作成前に人数、参照、theme語彙、character割当を検証する。CLIは`setup show`、`setup export`、
`setup validate`、`setup inspect`と`game create --setup-file`を提供する。

`setup validate`と`setup inspect`は`POST /api/v1/setups/validate`を呼び、ゲーム作成と同じ
application validatorで参照、余剰定義、theme網羅性を確認する。構文だけを確認して有効とは
判定しない。

React clientは現時点ではsetup metadataの参照とpreset作成を担当し、詳細editorは提供しない。
