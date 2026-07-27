# Werewolf Agent

Werewolf Agent は、LLM agent を人狼ゲームのプレイヤーとして動かす backend です。
READMEの最短導線に続く、設計、公開API、開発、検証、release、運用の正本です。
現在のsource、設定、生成契約、品質成果物を根拠とし、調査履歴とは分離します。

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

/notes/index
```

## 読み方

- 初めて実行する場合はrepositoryの`README.md`から始めます。
- 利用目的と提供範囲を確認する場合は、{ref}`requirements` から読みます。
- コードの配置と依存方向を確認する場合は、{ref}`system-architecture` から読みます。
- 変更の進め方は、{ref}`development` と {ref}`verification` を参照します。
- 起動、診断、復旧は、{ref}`operations` を参照します。
- 品質command、Browser E2E、Agent reviewの具体的な操作は`scripts/README.md`を正とします。
