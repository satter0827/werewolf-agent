# Application

applicationはユースケース、DTO、projection、repository portを所有します。

- `GameApplication`を公開facadeにする。
- application command、query、resultとportを所有し、HTTP request schemaを参照・公開しない。
- game参照、player observation、player action、非同期operation受付は`AccessPolicy`を必ず通す。
- workerが計算した進行結果のcommitも、actorを受け取るfacade経由で認可する。
- adapterは認可資料とqueue機能を提供し、許可するユースケースを決定しない。
- handlerはゲーム参照、進行、player action、timelineの変更単位で分ける。
- DTOはcontext、request、result、persistence recordのlifecycleで分ける。
- domain操作、認可、保存、projectionだけを調整する。
- agents、adapters、clients、loggingへ依存しない。
- 外部実装が必要な境界はProtocolとして定義する。
- 標準gameの`player_id`は`player-1`から始まる連番として生成する。
