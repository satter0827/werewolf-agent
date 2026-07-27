# Streamlit Browser QA

## 起動

`Run: Streamlit Stack`または次の標準URLを使用する。

- Streamlit: `http://127.0.0.1:8501`
- API health: `http://127.0.0.1:8000/health`

先にReleaseの自動Browser E2Eを成功させ、成果物のcontact sheet、個別画像、console、network、
accessibility結果を確認する。

## desktop

- 開始設定の4領域とvalidationを確認する。
- gameを開始し、status、卓、入力、対象選択、公開timelineを確認する。
- 完了結果が公開timelineより前に表示され、進行操作が消えることを確認する。
- 観戦、記録、表示設定へkeyboardで移動できることを確認する。

## mobile

- 390×844と320×844で確認する。
- 横方向のoverflowがなく、主要操作が44px以上であることを確認する。
- sidebar、status、卓、操作、timelineのDOM順と表示順が一致することを確認する。

## AI画面確認

Browser画面確認スキルでdesktopとmobileの主要状態を操作し、自動E2E画像と実画面を照合する。
スキルを利用できない場合はAI画面レビューだけを`blocked`とし、自動E2Eの成否は変更しない。
