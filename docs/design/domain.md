(domain-model)=
# ドメインモデル

`werewolf_agent.domain` はゲームルールと状態遷移を所有する。外部サービス、永続化、
画面、LLM provider の都合を持ち込まず、同じ初期状態と操作から同じ結果を返す。

## 集約

`Game` がゲーム状態を変更できる唯一の集約である。参加者、役職、フェーズ、投票、
夜行動、勝敗を一貫した単位として検証し、成功した操作をイベントとして記録する。
applicationやclientは合法手や勝敗を再計算しない。

```{image} ../_generated/architecture/domain-structure.svg
:alt: Game 集約とルール、状態、イベントの関係
:class: architecture-diagram
```

## 状態と公開情報

完全なゲーム状態には役職や夜行動などの秘匿情報を含む。通常の外部出力は公開状態と
public timeline に射影し、player observation は認証した本人が知り得る範囲へ
絞る。完全状態の管理者 reveal、ゲーム終了後の完全リプレイ、LLM trace は、公開
DTO とは別の認可された経路で扱う。

## ルール

ルールの可変部分は登録済み policy ID と設定値で選択する。設定ファイルに Python
import path や独自 DSL を記述しない。policy は状態を保持せず、状態変更は `Game`
へ集約する。

設定読み込み時には、役職、フェーズ、policy ID、数値範囲、相互参照を検証する。
不正な定義をゲーム開始後まで持ち越さない。

## イベント

イベントは状態遷移の結果を表し、完全リプレイと公開 timeline の入力になる。
コマンドの意図と結果を区別し、失敗した操作を成功イベントとして残さない。

## 保証

- domain は他のプロジェクト層へ依存しない。
- file I/O、環境変数、logging、database、HTTP、LLM provider に依存しない。
- ランダム性を使う処理は seed または明示した乱数源で再現できる。
- public state と public timeline は秘匿情報を含まない。
- ルール、勝敗、投票、夜行動は unit test で状態遷移を直接検証する。
