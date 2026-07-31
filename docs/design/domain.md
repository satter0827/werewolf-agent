(domain-model)=
# ドメインモデル

`werewolf_agent.domain`はゲームルールと状態遷移を所有する。外部サービス、永続化、
画面、LLM providerの都合を持ち込まず、同じ初期状態と操作から同じ結果を返す。

## 集約

`Game`がゲーム状態を変更できる唯一の集約である。参加者、役職、フェーズ、投票、
夜行動、勝敗を一貫した単位として検証し、成功した操作をイベントとして記録する。
applicationやclientは合法手や勝敗を再計算しない。
状態、設定、action、event、viewは凍結dataclass、tuple、読み取り専用mappingで表し、
snapshotを受け取った側から変更できない。`player_id`はゲーム内で一意な非空文字列であり、
domainはID生成規則とuserの所有関係を扱わない。
復元時にもプレイヤー数、mapping key、役職構成、終局結果、pending actionの参照整合を検証する。
プレイヤー mappingはID順へ正規化し、保存形式のobject順序に状態遷移を依存させない。

```{image} ../_generated/architecture/domain-structure.svg
:alt: Game集約とルール、状態、イベントの関係
:class: architecture-diagram
```

## 状態と公開情報

完全なゲーム状態には役職や夜行動などの秘匿情報を含む。通常の外部出力は公開状態と
public timelineに射影し、プレイヤー observationは認証した本人が知り得る範囲へ
絞る。完全状態の管理者reveal、ゲーム終了後の完全リプレイ、LLM traceは、公開
DTOとは別の認可された経路で扱う。
本人用`GameView`の発言履歴は公開messageと参照IDだけを保持し、内部reasonを保持しない。
終局結果は勝利陣営、公開理由、日数だけを保持し、完全状態の勝利プレイヤーIDを含めない。
`reveal_role_on_death`が有効な場合だけ、死亡が確定したプレイヤーのroleとfactionをpublic stateと
対応する解決済みeventへ含める。生存者、未解決投票、夜行動、占い結果は公開しない。

## ルール

ルールの可変部分は登録済みpolicy IDと設定値で選択する。設定ファイルにPython
import pathや独自DSLを記述しない。policyは状態を保持せず、状態変更は`Game`
へ集約する。

設定読み込み時には、役職、フェーズ、policy ID、数値範囲、相互参照を検証する。
不正な定義をゲーム開始後まで持ち越さない。

## イベント

イベントは状態遷移の結果を表し、完全リプレイと公開timelineの入力になる。
コマンドの意図と結果を区別し、失敗した操作を成功イベントとして残さない。

## 保証

- domainは他のプロジェクト層へ依存しない。
- domainはPydanticを含む第三者packageへ依存しない。
- file I/O、環境変数、logging、database、HTTP、LLM providerに依存しない。
- ランダム性を使う処理はseedまたは明示した乱数源で再現できる。
- public stateとpublic timelineは秘匿情報を含まない。
- ルール、勝敗、投票、夜行動はunitテストで状態遷移を直接検証する。
