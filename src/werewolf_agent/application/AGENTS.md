# Application

applicationはユースケース、DTO、projection、repository portを所有します。

- `GameApplication`を公開facadeにする。
- handlerはゲーム参照、進行、player action、timelineの変更単位で分ける。
- DTOはcontext、request、result、persistence recordのlifecycleで分ける。
- domain操作、認可、保存、projectionだけを調整する。
- agents、adapters、clients、loggingへ依存しない。
- 外部実装が必要な境界はProtocolとして定義する。
