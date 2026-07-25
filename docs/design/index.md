# 設計書

設計書は、利用者の要求がどの境界で実装され、どの検証を通り、どの自動化入口で
運用されるかを説明する。コード、設定、生成契約、品質成果物を根拠とし、
同じ事実を複数の章で定義しない。

```{toctree}
:maxdepth: 2

requirements
architecture
domain
application-and-api
agents
data-and-security
clients
configuration-and-runtime
development
verification
build-and-release
operations
```

## 責務別の入口

| 関心 | 文書 |
| --- | --- |
| 製品が満たす要求 | {ref}`requirements` |
| component と依存方向 | {ref}`system-architecture` |
| ゲームルールと状態遷移 | {doc}`domain` |
| HTTP、worker、永続化 | {doc}`application-and-api` |
| LLM agent | {doc}`agents` |
| 秘密情報と replay | {doc}`data-and-security` |
| 開発と検証 | {ref}`development`、{ref}`verification` |
| release と運用 | {ref}`build-release`、{ref}`operations` |
