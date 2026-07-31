(python-api-reference)=
# Python API

`werewolf_agent.domain`はゲーム規則、明示登録するRule Pack、決定的な状態遷移を提供する。
`werewolf_agent.setup`は完全setupの検証、Domain Rule Definition変換、用途別seed、checksum、
プレイヤー generationを提供する。
`werewolf_agent.agents`は外部Agentの注入契約と標準Agent実装を提供する。
`werewolf_agent.simulation`は単一ゲームのstep実行、停止、再開を提供する。
`werewolf_agent.experiments`は比較条件と決定的なTrial計画を提供する。
`werewolf_agent.application`は認可、保存port、公開resultを含む利用手順を提供する。
列挙されない内部モジュールは公開契約に含めない。

## Package

`werewolf_agent`は`__version__`だけを公開する。型と関数は責務を所有するモジュールからimportする。

```{eval-rst}
.. automodule:: werewolf_agent
```

## Domainの最小利用例

`Action`はdomainへ渡す検証済みのプレイヤー操作を表す。構築時の不正な値は`ValueError`で
通知する。

```{literalinclude} ../snippets/python_api_domain.py
:language: python
```

## Applicationの最小利用例

`create_embedded_application()`は設定、setup catalog、任意のリポジトリとRule Packを受け取り、
HTTP、database、workerを必要としないsingle-tenant applicationを構築する。設定とcatalogは暗黙に
読み込まず、利用者が実験条件として固定する。`InlineCommandExecutor`は型付きコマンドをqueueなしで
同期実行する。状態はfactoryやfacadeではなく、注入したリポジトリが所有する。

```{literalinclude} ../snippets/python_api_application.py
:language: python
```

## Setupの最小利用例

`GameSetupDocument.from_mapping()`はJSON互換値をimmutableなsetupへ変換する。
`to_rule_definition()`でdomain規則を構築でき、同じプレイヤー generation定義とseedから同じrosterを
生成する。

```{literalinclude} ../snippets/python_api_setup.py
:language: python
```

## Agentの最小利用例

`AgentFactory`はgameとプレイヤーごとに状態を共有しない`AgentSession`を生成する。
標準Agentは本人用observationと合法候補から、同じdecision seedに対して同じ応答を返す。

```{literalinclude} ../snippets/python_api_agents.py
:language: python
```

## Domain API

```{eval-rst}
.. automodule:: werewolf_agent.domain
   :members:
```

## Application API

```{eval-rst}
.. automodule:: werewolf_agent.application
   :members:
```

## Setup API

```{eval-rst}
.. automodule:: werewolf_agent.setup
   :members:
```

## Agent API

```{eval-rst}
.. automodule:: werewolf_agent.agents
   :members:
```

## Simulationの最小利用例

`SimulationSpec`はproviderや永続化へ依存せず、一局のcontrollerとseedを固定する。
構築済みの`Game`は`SimulationRunner.start()`へ渡す。

```{literalinclude} ../snippets/python_api_simulation.py
:language: python
```

## Simulation API

```{eval-rst}
.. automodule:: werewolf_agent.simulation
   :members:
```

## Experimentの最小利用例

`ExperimentSpec`はRules比較とAgent比較を混在させず、seedと割当rotationを固定する。

```{literalinclude} ../snippets/python_api_experiments.py
:language: python
```

## Experiment API

```{eval-rst}
.. automodule:: werewolf_agent.experiments
   :members:
```
