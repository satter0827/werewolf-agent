# Werewolf Agent

Werewolf Agentは、LLMエージェントを人狼ゲームのプレイヤーとして動かすPython
バックエンドである。この文書は、設計、公開API、開発、検証、リリース、運用の正本として、
現在のソースコード、設定、生成契約、品質成果物を説明する。

::::{grid} 1 2 2 2
:gutter: 2

:::{grid-item-card} 製品と要件を理解する
:link: design/requirements
:link-type: doc

利用者、機能要件、品質要件、提供範囲を確認する。
:::

:::{grid-item-card} 構造と境界を確認する
:link: design/architecture
:link-type: doc

レイヤー、依存方向、公開面、生成された構造図を確認する。
:::

:::{grid-item-card} 開発と検証を進める
:link: design/development
:link-type: doc

変更の進め方、品質判定、成果物の読み方を確認する。
:::

:::{grid-item-card} 起動・診断・運用を行う
:link: design/operations
:link-type: doc

実行プロセス、監視信号、問題調査、外部運用境界を確認する。
:::
::::

```{toctree}
:maxdepth: 2
:hidden:

/design/index
```

```{toctree}
:maxdepth: 2
:hidden:

/reference/index
```

```{toctree}
:maxdepth: 1
:hidden:

/notes/index
```

## 文書の使い分け

- 初めて実行する場合は、リポジトリの`README.md`から始める。
- 公開Python APIと実行時設定は、{ref}`reference`を参照する。
- 品質コマンド、ブラウザーE2E、エージェントレビューの具体的な操作は、`scripts/README.md`を正本とする。
- 過去の設計判断は、{doc}`notes/index`から参照する。決定済み仕様としては扱わない。
