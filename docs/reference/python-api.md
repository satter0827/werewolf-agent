(python-api-reference)=
# Python API

`werewolf_agent.domain`はゲーム規則と決定的な状態遷移を提供する。
`werewolf_agent.setup`は完全setupの検証、Domain Rule Definition変換、用途別seed、checksum、
プレイヤー generationを提供する。
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

`GameApplication`は外側で構築したportと設定を受け取る。予定された失敗は`AppError`系で返し、
利用者は`ErrorCode`で処理を分岐できる。

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
