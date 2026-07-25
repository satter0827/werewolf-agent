# Domain

domainはゲームの完全状態、event、rule、`Game` aggregateを所有します。

- stdlibとdomain内部だけに依存する。
- I/O、設定読込み、Pydantic、logging、database、LLMを持ち込まない。
- 失敗した操作でstateとeventを変更しない。
- seedとactionから同じstateとeventを再現できるようにする。
