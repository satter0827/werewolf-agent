# 設計書

設計書は、利用者の要求がどの境界で実装され、どの検証を通り、どの自動化入口で
運用されるかを説明する。コード、設定、生成契約、品質成果物を根拠とし、同じ事実を
複数のページで定義しない。

具体的なデフォルトと環境変数はsettings、HTTP wire schemaは`contracts/openapi.json`、
構造規則は`scripts/architecture/rules.toml`、開発操作は`scripts/README.md`を正本とする。

```{toctree}
:maxdepth: 1
:hidden:

requirements
architecture
domain
game-setup
application-and-api
agents
data-and-security
clients
configuration-and-runtime
development
verification
evidence-and-diagnostics
build-and-release
operations
```

## 責務別の入口

| 関心 | 文書 |
| --- | --- |
| 製品が満たす要求 | {ref}`requirements` |
| コンポーネントと依存方向 | {ref}`system-architecture` |
| ゲームルールと状態遷移 | {doc}`domain` |
| HTTP、worker、永続化 | {doc}`application-and-api` |
| LLMエージェントと自動進行 | {doc}`agents` |
| 秘密情報とリプレイ | {doc}`data-and-security` |
| 開発と検証 | {ref}`development`、{ref}`verification` |
| 品質証拠と診断 | {ref}`evidence-diagnostics` |
| リリースと運用 | {ref}`build-release`、{ref}`operations` |
