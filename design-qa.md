# Streamlit 月明かりの卓 Design QA

## 比較対象

- 参照デザイン: `C:\Users\brts5\.codex\generated_images\019f9de2-2aee-73a1-9f05-bd4ba418fbff\exec-84890636-f71d-4800-9388-bca08c3be58e.png`
- 実装画面: `C:\Users\brts5\source\portfolio\werewolf-agent\.werewolf-agent\quality\failures\gate-e2e\20260727T013551Z-gate-e2e-3392\browser\test-results\streamlit-Streamlit-comple-79189-ents-result-before-timeline-desktop\streamlit-gameplay-complete-desktop.png`
- 同一比較画像: `C:\Users\brts5\.codex\visualizations\2026\07\26\019f9de2-2aee-73a1-9f05-bd4ba418fbff\moonlit-tableau-comparison.png`
- 比較viewport: 1280×720

## 視覚監査

- sidebar、6項目status ribbon、卓と操作rail、公開timelineの情報階層は参照デザインと一致する。
- アイボリーを基調に、藍、深緑、琥珀、鈍い赤を状態表現へ限定している。
- 装飾画像、texture、gradient、強いshadowを使わず、余白、枠、状態markerで人狼の卓を表現している。
- 独立cardの集合ではなく、player seatを一つのtableau surfaceへまとめている。
- 8/16/24/32/48pxの余白体系により、入力、関連操作、情報群、主要sectionの密着を解消している。
- desktopはstatus 6列、tableau 70%、操作rail 30%。mobileはstatus 2列、seat 2列で、DOM順と視覚順が一致する。
- 完了時は結果サマリーを公開timelineより前に表示し、不要な進行操作を表示しない。

## 動作・アクセシビリティ

- Streamlit Playwright 10ケースはdesktop/mobileですべて成功した。
- 1280×720、390×844、320pxでhorizontal overflowがない。
- 可視buttonとtabは44px以上で、keyboard focusを視認できる。
- heading順、入力label、重大・深刻なAxe違反ゼロ、外部network要求ゼロを確認した。
- 開始設定4tabs、validation、待機、発言、対象選択、送信進行、完了、observer、Records、Settingsを確認した。

## 解消事項

- P0: なし。
- P1: 全体gapの一括指定、画面構造の三重管理、独自HTMLの過剰利用を解消した。
- P2: section密着、結果見出しの階層飛び、mobile sidebarのpointer座標依存を解消した。

final result: passed
