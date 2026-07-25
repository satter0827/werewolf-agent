# Werewolf Agent Docs

Werewolf Agent は、LLM agent を人狼ゲームのプレイヤーとして動かす Python backend です。
完成版の設計書は `docs/design/`、作業メモは `docs/notes/` に分けています。

```{toctree}
:maxdepth: 2
:caption: Design

/design/domain
/design/api
/design/quality-gates
/design/second-stage-architecture
/design/security-and-persistence
/design/ui-and-browser-qa
/design/runtime-and-docker
/design/python-api
/design/agent-strategies
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
2. [第二段階Architecture](../design/second-stage-architecture.md): 層と依存方向
3. [API](../design/api.md): 公開 API 契約
4. [品質ゲート](../design/quality-gates.md): 実行level、判定、成果物、offline境界
5. [SecurityとPersistence](../design/security-and-persistence.md): 認証、秘匿、再現性
6. [UIとBrowser QA](../design/ui-and-browser-qa.md): React、Streamlit、画面検証
7. [RuntimeとDocker](../design/runtime-and-docker.md): 設定と起動
8. [Python API](../design/python-api.md): `GameApplication`
9. [Development](../notes/development.md): 再開メモと実行コマンド
