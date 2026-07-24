# 境界と公開契約

## 目的

画面、Supabase、LLM、ゲームルールを一方向の依存関係で接続します。外部クライアントは`GameClient`、アプリケーション内部はステートレスなusecase関数、ゲームルールは`Game`集約ルートを利用します。

DBスキーマ、migration、Supabase Data APIの保存方式は変更しません。アダプターが既存レコードと新しい`GameState`を機械的に変換します。

## 責務

| 層 | 責務 |
| --- | --- |
| `interfaces` | CLI、Streamlit、workerの入力と表示 |
| `adapters` | `GameClient`、Supabase、repository、LLM game driver |
| `usecase` | IDを含む要求、取得、復元、domain呼び出し、DTO変換 |
| `domain` | ゲームルールと状態遷移 |
| `agents` | provider非依存の判断契約とLangChain実装 |
| `configuration` | 環境変数、TOML、packaged defaultの読込と検証 |
| `observability` | 境界ログ、イベント、実行コンテキスト |
| `security` | 秘密情報のマスキング |
| `contracts` | 外部wire schema、error code、Problem Details |

## データフロー

```text
interfaces
  -> GameClient
  -> adapters
  -> usecase function
  -> Game
  <- state + typed events
  <- immutable result
  <- public wire schema

自動プレイヤー:
adapters -> PlayerAgent -> AgentDecision -> Game(Action)
```

自動プレイヤーの接続は`adapters/agents/game_driver.py`に限定します。agentsはdomainが提示した合法対象から候補を返し、domainが提出時に再検証します。LLM失敗時は同じ判断パイプラインのfallbackが合法候補を選びます。

## GameClient

interfacesが参照できるクライアント契約は次だけです。

```python
from werewolf_agent.adapters import GameClient, build_game_client
```

`GameClient`は作成、取得、進行、一覧、timeline、player observation、manual action、管理者revealの外部操作を定義します。Supabase実装はoperation requestをenqueueし、Data APIから結果を取得します。

認証前提はSupabase anonymous sessionです。manual playerの権限は`game_participants.auth.uid()`とRLSを正とし、画面固有tokenやseat credentialを作りません。

## Usecase

usecaseの基本公開面はモジュールレベル関数と不変の`UsecaseContext`です。

```python
create_game(context, command)
submit_player_action(context, command)
advance_game(context, command)
get_game(context, query)
get_player_observation(context, query)
```

`UsecaseContext`へrepository、検証済み定義、運用上限を注入します。各関数は共有状態を持たず、ログやテレメトリーも出力しません。呼び出しごとに次を行います。

1. IDと利用者要求を検証する
2. repositoryから現在状態を取得する
3. `Game.restore()`でdomainを復元する
4. domainの公開操作を呼ぶ
5. revisionを確認して結果を保存する
6. public DTOまたはprivate DTOへ変換する

usecaseには役職、フェーズ、行動対象、勝敗の条件分岐を置きません。
LLMのprovider設定とtrace sinkも`UsecaseContext`へ入れず、`adapters/agents/game_driver.py`の`AgentRuntime`が保持します。

## Agents

公開契約は`PlayerAgent`、`AgentObservation`、`AgentDecision`です。ゲームの内部状態を型として共有しません。

LangChainとLangGraphの具体実装は`agents/langchain`に限定します。fake providerも独自クラスを作らず、LangChain標準の`FakeListLLM`を使用します。fakeと実providerは、prompt構築、構造化出力、検証、再試行、fallbackを共有します。

設定で変更できる項目:

- provider種別
- model名と接続先
- timeout、retry、temperature、max tokens
- decision graph
- prompt
- fake応答列
- validation retryとfallback方針

provider固有の新しい通信方式や新しいgraph nodeはPython実装を必要とします。

## 公開情報と秘密情報

| 出力先 | 許可する情報 |
| --- | --- |
| public state | フェーズ、日数、生死、勝者 |
| public timeline | 公開発言、解決後の投票結果、公開死亡結果 |
| player observation | 本人が観測できる役職、能力、合法候補 |
| admin reveal | 管理者専用の完全状態 |
| LLM trace | 管理者専用のprompt、応答、解析結果 |
| operational log | ID、処理結果、所要時間、外部障害の分類 |

public responseとログへ、秘密役職、夜行動対象、占い結果、API key、token、prompt、LLM生出力を出しません。
各プレイヤーの投票提出と投票先は解決前に公開せず、集計済みの結果だけをpublic timelineへ出します。

## ログ

domainとusecaseはログを出しません。interfacesとadaptersが外部境界で一度だけ記録します。

| Level | 用途 |
| --- | --- |
| `DEBUG` | 状態遷移、設定解決、エージェント判断の安全な要約 |
| `INFO` | プロセス開始・終了、ゲーム作成、フェーズ完了、ゲーム終了 |
| `WARNING` | 外部サービスの一時障害、再試行、縮退 |
| `ERROR` | 継続不能な外部障害、不正設定、予期しない例外 |

入力不備、存在しないID、通常のルール違反は結果として返し、エラーログにしません。ログ名は実行機能に合わせて`worker.jsonl`、`streamlit.jsonl`、`cli.jsonl`、`migrate.jsonl`とします。

## 永続化

- Supabaseを永続化の正本とする
- public schemaとprivate schemaの既存分離を維持する
- workerだけがprivate stateとLLM traceを書き込む
- optimistic revisionを維持し、状態競合を通常の結果として扱う
- public timelineをdomainの型付きイベントから投影する
- DBスキーマとmigrationは今回変更しない

## 構造制約

- interfacesはdomainとusecaseを直接importしない
- adaptersはinterfacesへ依存しない
- usecaseはadapters、interfaces、agentsへ依存しない
- agentsはdomainとusecaseへ依存しない
- domainは他のプロジェクト層へ依存しない
- 外部層は`werewolf_agent.domain`の公開面を使用する
- import許可表と循環参照はASTベースの構造テストで検査する

## エラー契約

domainの`RuleViolation`はusecaseが外部エラー契約へ変換します。外部には安全なerror code、利用者向けメッセージ、必要最小限のcontextだけを返します。内部例外、stack trace、認証情報は返しません。
