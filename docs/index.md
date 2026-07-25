# Werewolf Agent

Werewolf Agent は、LLM agent を人狼ゲームのプレイヤーとして動かす backend です。
この文書は、要件、設計、開発、検証、release、運用の順に、システムの責務と
判断根拠を説明します。

```{toctree}
:maxdepth: 2
:caption: Design

/design/index
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

## 読み方

- 利用目的と提供範囲を確認する場合は、{ref}`requirements` から読みます。
- コードの配置と依存方向を確認する場合は、{ref}`system-architecture` から読みます。
- 変更の進め方は、{ref}`development` と {ref}`verification` を参照します。
- 起動、診断、復旧は、{ref}`operations` を参照します。
