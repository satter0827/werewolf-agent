# Python API

## 公開面

Pythonからusecaseを利用する入口は`Actor`と`GameApplication`だけです。

```python
from werewolf_agent.contracts import CreateGameRequest
from werewolf_agent.usecase import Actor, GameApplication

games = GameApplication(context)
actor = Actor(user_id="user-id")

created = games.create(
    CreateGameRequest(
        seed=1,
        role_counts={"werewolf": 1, "seer": 1, "knight": 1, "villager": 2},
    )
)
current = games.get(created.game_id, actor)
history = games.timeline(created.game_id, actor, cursor=0)
```

`GameApplication`は構築時の依存関係だけを保持し、game状態や利用者sessionを保持しません。各呼び出しはrepository transactionの範囲で実行します。
入力は公開contractまたは基本型だけを使用し、内部のcommand、query、repository DTOを
importする必要はありません。
`create`はprovider、model、LLM modeを受け取りません。通常のPython利用では安全なfakeを
使用し、HTTP workerだけが検証済みの利用者区分を内部依存として注入します。

提供する操作:

- `create`
- `get`
- `list`
- `submit_action`
- `advance`
- `timeline`
- `observation`
- `reveal`
- `verify_replay`

handler、repository DTO、永続化modelは内部実装です。互換aliasは提供しません。`werewolf_agent.usecase.__all__`は構造テストで完全一致を確認します。
