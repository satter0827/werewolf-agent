# Werewolf Agent

Werewolf Agentは、LLMエージェントを人狼ゲームのプレイヤーとして動かすPythonバックエンドである。
決定的なdomain core、公開Python SDK、HTTP API、worker、CLI、Streamlitを提供する。

::::{grid} 1 2 2 2
:gutter: 2

:::{grid-item-card} 利用者と機能
:link: design/requirements
:link-type: doc

提供機能、利用者、品質要件、1.0.0の範囲を示す。
:::

:::{grid-item-card} システム構造
:link: design/architecture
:link-type: doc

外部サービス、実行プロセス、Pythonパッケージ、依存方向を示す。
:::

:::{grid-item-card} 開発と検証
:link: design/development
:link-type: doc

変更単位、品質判定、構造検査、成果物を示す。
:::

:::{grid-item-card} 起動と運用
:link: design/operations
:link-type: doc

実行プロセス、監視信号、障害調査、外部運用境界を示す。
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

## 入口

- 最初の実行はリポジトリの`README.md`を使用する。
- 公開Python APIと実行時設定は{ref}`reference`を使用する。
- 品質、環境、ブラウザーE2E、レビューの操作は`scripts/README.md`を使用する。
- 実装済み仕様は{doc}`design/index`、未完了の検討は{doc}`notes/index`に分ける。
