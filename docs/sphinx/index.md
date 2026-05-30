# Werewolf Agent Docs

Werewolf Agent は、LLM agent を人狼ゲームのプレイヤーとして動かす Python backend です。
完成版の設計書は `docs/design/`、作業メモは `docs/notes/` に分けています。

```{toctree}
:maxdepth: 2
:caption: Design

/design/domain
/design/api
```

```{toctree}
:maxdepth: 2
:caption: Reference

/reference/index
```

```{toctree}
:maxdepth: 1
:caption: Notes

/notes/development
/notes/streamlit-ui
/notes/streamlit-ui-design-history
/notes/streamlit-browser-qa
```

## 読む順番

1. [Domain](../design/domain.md): domain core と境界
2. [API](../design/api.md): 公開 API 契約
3. [Development](../notes/development.md): 再開メモと実行コマンド
