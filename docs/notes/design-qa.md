# Streamlit月明かりの卓 Design QA

## 視覚監査

- sidebar、6項目のstatus ribbon、卓、操作rail、公開timelineの順に情報を配置する。
- アイボリーを基調に、藍、深緑、琥珀、鈍い赤を状態表現へ限定する。
- player seatを一つのtableauへまとめ、独立cardの集合にしない。
- desktopはstatus 6列、tableau 70%、操作rail 30%とする。
- mobileはstatus 2列、seat 2列とし、DOM順と視覚順を一致させる。
- 完了時は結果サマリーを公開timelineより前に表示し、進行操作を表示しない。

## 動作とaccessibility

- desktop、mobile、320px幅でhorizontal overflowを発生させない。
- 可視buttonとtabは44px以上とし、keyboard focusを視認可能にする。
- heading順、入力label、重大なAxe違反、外部network要求を自動Browser検査で確認する。
- 開始設定、validation、待機、発言、対象選択、進行、完了、観戦、記録、設定を確認する。

## 判定

自動Browser検査の成果物とBrowser画面確認スキルの実画面を照合して判定する。
