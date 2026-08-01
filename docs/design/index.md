# 設計書

Werewolf Agentの実装済み要件、構造、処理、保証を現在形で定義する。具体的なデフォルトと環境変数は
settings、HTTP wire schemaは`contracts/openapi.json`、構造規則は`scripts/architecture/rules.toml`、
開発操作は`scripts/README.md`を使用する。

```{toctree}
:maxdepth: 1
:hidden:

requirements
architecture
domain
game-setup
application-and-api
agents
simulation
experiments
data-and-security
clients
configuration-and-runtime
development
verification
evidence-and-diagnostics
build-and-release
operations
```

## 読む順序

| 知りたいこと | 参照先 |
| --- | --- |
| 利用者と提供機能 | {ref}`requirements` |
| 外部サービス、実行プロセス、Pythonパッケージ | {ref}`system-architecture` |
| ゲーム状態、phase、Rule Pack | {doc}`domain` |
| setup、seed、プレイヤー生成 | {doc}`game-setup` |
| HTTP request、認可、queue、worker | {doc}`application-and-api` |
| Agent observationと意思決定 | {doc}`agents` |
| 一局のheadless実行 | {doc}`simulation` |
| 反復試行と評価 | {doc}`experiments` |
| public、本人用、private情報 | {doc}`data-and-security` |
| CLIとStreamlit | {doc}`clients` |
| 設定と実行環境 | {doc}`configuration-and-runtime` |
| 変更、検証、証拠、リリース | {ref}`development`、{ref}`verification`、{ref}`evidence-diagnostics`、{ref}`build-release` |
| 起動、監視、障害調査 | {ref}`operations` |
