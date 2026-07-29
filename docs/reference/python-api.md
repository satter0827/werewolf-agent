(python-api-reference)=
# Python API

`werewolf_agent.domain`はゲーム規則と決定的な状態遷移を提供する。
`werewolf_agent.application`は認可、保存port、公開resultを含む利用手順を提供する。
列挙されない内部モジュールは公開契約に含めない。

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
