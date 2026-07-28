# Domain

`domain`はゲームの完全状態、event、rule、`Game` aggregateを所有する。

- stdlibとdomain内部だけに依存する。
- I/O、設定読込み、Pydantic、logging、database、LLMを持ち込まない。
- `Game`、`GameState`、`GameSetup`、`Action`、`GameEvent`、`GameView`を正規概念とし、
  wire schemaや同義aliasを置かない。
- snapshot、view、eventは外部から変更できない値として返す。
- `player_id`はゲーム内で一意な非空文字列として扱い、生成規則とuser所有関係を持たない。
- 失敗した操作でstateとeventを変更しない。
- seedとactionから同じstateとeventを再現できるようにする。
