# Domain 設計

## 目的

`domain`は、人狼ゲームの状態遷移を外部サービスなしで実行できるヘッドレスコアです。画面、ID検索、永続化、設定ファイル、ログ、LLMを知りません。同じ初期値、seed、行動列を与えれば、同じ状態とイベント列を返します。

`usecase`は利用者の要求をdomainへ接続する層です。ゲームIDから状態を取得し、domainを復元して操作し、結果を保存用DTOへ変換します。フェーズ、役職、対象条件、勝敗を判定しません。

## 責務

### Domain

- ゲームの作成、復元、行動受付、フェーズ進行を行う
- 行動の合法性、必須行動、解決順、勝敗、可視性を判定する
- 状態変更を型付きイベントとして返す
- 失敗時に状態を変更せず、`RuleViolation`を返す

### Usecase

- ID、revision、ページングなどの利用者要求を検証する
- repositoryから状態を取得し、domainを復元する
- domain操作の結果を保存用・公開用DTOへ変換する
- 外部から注入されたrepositoryと設定済み定義だけを使う

### Agents

- 公開された観測から候補行動を生成する
- provider、prompt、graph、retry、fallbackを扱う
- ゲーム状態や役職の真実を保持せず、合法性を最終判断しない

## 公開面

domainの公開面は次に限定します。

```python
from werewolf_agent.domain import (
    Action,
    Game,
    GameEvent,
    GameSetup,
    GameState,
    GameView,
    RuleRegistry,
    RuleSet,
    RuleSetDefinition,
    RuleViolation,
)
```

基本操作は`Game`集約ルートを経由します。

```python
rules = registry.build(definition)
game = Game.create(setup, rules=rules, random=random_source)
game = Game.restore(state, rules=rules)

events = game.submit(action)
events += game.advance(random_source)

view = game.view_for(player_id)
state = game.snapshot()
```

`GameState`は未解決行動も含む完全かつ不変のスナップショットです。`Game.restore()`はこの状態だけから集約を復元します。`submit()`と`advance()`は遷移全体が成功した場合だけ内部状態を置き換えます。検証失敗時は`RuleViolation`を送出し、状態を変更しません。

## クラス構成

```text
RuleRegistry --build--> RuleSet <--uses-- Game
                           |
                           +-- ActionPolicy
                           +-- ResolutionPolicy
                           +-- PhasePolicy
                           +-- VictoryPolicy
                           +-- VisibilityPolicy

Game
  + create(setup, rules, random)
  + restore(state, rules)
  + submit(action) -> GameEvent[]
  + advance(random) -> GameEvent[]
  + view_for(player_id) -> GameView
  + snapshot() -> GameState
```

役職ごとのクラスは作りません。役職は陣営と能力IDの組み合わせで表し、能力は利用フェーズ、対象条件、解決ポリシーなどの値で表します。既存アルゴリズムのパラメーター変更は設定で行い、新しいアルゴリズムだけをポリシー実装として追加します。

## ポリシー

| ポリシー | 判定内容 | 既定実装 |
| --- | --- | --- |
| `ActionPolicy` | 行動者、対象、回数、生存条件、利用可能行動、合法対象 | `standard` |
| `ResolutionPolicy` | 投票、襲撃、護衛、占いの効果 | `standard` |
| `PhasePolicy` | 必須行動と次フェーズ | `required_actions` |
| `VictoryPolicy` | 陣営の全滅と人数均衡 | `faction_balance` |
| `VisibilityPolicy` | プレイヤー別観測と履歴の公開範囲 | `standard` |

`RuleRegistry`はポリシーIDとfactoryを明示登録します。設定ファイルにPythonクラス名、import path、条件DSLは書きません。未知のIDは起動時またはルール構築時に拒否します。

## 設定可能範囲

| 設定だけで変更できること | Python実装が必要なこと |
| --- | --- |
| `night`、`day_discussion`、`voting`の順序と必須行動の有無 | フェーズの追加と新しい状態遷移方式 |
| 行動回数、自己対象、再提出の許可 | 新しい対象判定アルゴリズム |
| 初夜襲撃、同票時処理の既存選択肢 | 新しい投票集計アルゴリズム |
| 役職の陣営、能力ID、既定人数、能力の開始日と登録済み対象条件 | 新しい能力効果と利用フェーズ |
| 登録済みポリシーの組み合わせ | 新しい勝敗・可視性アルゴリズム |
| 背景、表示名、説明、ナレーション | 新しい外部サービス連携 |

設定の正本は次のとおりです。

| ファイル | 内容 |
| --- | --- |
| `resources/game/rules.toml` | ルール値と登録済みポリシー構成 |
| `resources/game/roles.toml` | 役職、陣営、能力、既定人数 |
| `resources/game/abilities.toml` | 利用フェーズ、行動、対象、解決、開始日 |
| `resources/presentation/catalog.toml` | 背景、シナリオ、表示名、説明 |
| `resources/llm/` | provider以外のplayer、graph、fake応答 |
| `resources/prompts/` | LLM prompt |

`configuration`がTOMLと環境変数を読み、Pydanticで検証してから値を注入します。役職と能力、シナリオとナレーション、プリセットとシナリオ・役職の参照もロード時に検証します。既定プリセットは`game_default_setup_preset_id`で明示し、定義順には依存しません。domainはファイルパスや環境変数を受け取りません。

## 可視性

- public stateにはフェーズ、日数、生死、公開イベントだけを含める
- player viewにはそのプレイヤーが知る役職、能力、domainが検証した合法対象だけを含める
- public timelineには役職、夜行動、秘密の対象、占い結果を含めない
- 投票提出はplayer private eventとし、投票先と集計は投票解決後の公開結果だけに含める
- 画面とLLMには`GameView.legal_targets`を変換して渡し、対象条件を再計算させない
- operational logにはprompt、LLM生出力、認証情報、秘密状態を含めない

## 依存制約

```text
interfaces --> adapters --> usecase --> domain
                  |
                  +-------> agents

interfaces/adapters --> configuration
interfaces/adapters --> observability
interfaces/adapters --> security
```

- `domain`は他の層へ依存しない
- `usecase`は`agents`、`adapters`、`interfaces`へ依存しない
- `agents`はdomainとusecaseへ依存しない
- `adapters/agents/game_driver.py`だけがusecaseとagentsを接続する
- LangChainとLangGraphは`agents/langchain`以外からimportしない
- SupabaseとSQLAlchemyは`adapters/supabase`以外からimportしない
- StreamlitとTyperは`interfaces`以外からimportしない
- domainとusecaseはlogging、DB、file I/Oを行わない

これらは`tests/unit/architecture/test_architecture_boundaries.py`でimport許可表、モジュール循環、層循環、公開`__all__`、旧パス不在として検査します。

## 完了条件

- domain単体で作成から勝敗確定まで実行できる
- 必須行動不足と不正行動で状態が変化しない
- 同じseedと入力から同じイベント列を再現できる
- usecaseにゲームルールの分岐がない
- domain、agents、usecaseに相互参照がない
- 公開状態、履歴、LLM入力、ログへ秘密情報が漏れない
