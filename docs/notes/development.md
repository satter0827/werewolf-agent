# 開発メモ

## 目的

ゲームルールを外部サービスから独立したヘッドレスコアとして保ち、運用上変わる値を検証済み設定として注入します。画面、永続化、LLMはdomainの外側で接続します。

## 現在地

- 第二段階は`develope`の`c5427403`から分離worktreeで開始した
- React、Streamlit、CLIのゲーム通信をHTTP APIへ統一した
- `api`を独立させ、workerは実行interfaceとして`interfaces/worker`へ配置した
- Pythonのusecase公開面を`GameApplication`へ集約した
- Supabaseへcommand、event、snapshot、projection、checksumを保存するbaselineを追加した
- anonymous gameをFakeListLLM、ログインgameを有料providerへ作成時固定した
- React本番UIとStreamlit MOCへゲスト、ログイン、ログアウト導線を追加した
- JWT、認可、rate limit、body size、timeout、同時実行数、idempotency、version競合をAPI境界へ追加した
- idempotency keyの異なるrequestへの再利用をrequest hashで拒否するようにした
- 手動操作を含む全状態変更でversionを進め、履歴上書きを防止した
- `state_committed` eventからsnapshotとpublic projectionを検証できるようにした
- operation診断、LLM trace、利用量を管理APIへ隔離した
- 通常UIの`GameClient`からadmin revealを除去し、観戦表示をpublic timelineだけで
  構築するようにした
- Reactのprivate observation取得をプレイ画面だけへ限定し、観戦、履歴、設定では
  ブラウザへ秘匿データを渡さないようにした
- API rate limitを認証前のIPとJWT検証後の利用者・gameへ分離し、token refreshや
  game IDの変更による上限回避、未検証claimの悪用、任意キーによるbucketの
  無制限増加とactive bucketの追い出しを防止した
- Playwright testを`frontend/e2e`、migration・OpenAPI補助処理を`scripts`へ統合し、
  トップ階層の`e2e`と`tools`が再作成されないよう構造テストで固定した
- frontend開発依存を更新してnpm auditを0件にし、CIへ依存監査、生成client差分、
  unit test、lint、buildを追加した
- Dockerのtest imageへtestsを含め、test serviceをmigrationから独立させた。
  CIとローカルのunit testはSupabase未起動でも実際に収集・実行される
- Reactへ観戦専用game作成と完了結果を開く導線を追加し、Streamlitとの機能差を解消した
- 文章上限をAPIの型付き公開設定へ集約し、ReactとStreamlitが
  `limits.message_max_chars`を取得して同じ受理条件を使うようにした
- 既存gameのoperationは保存済みLLM modeをqueueで再解決し、途中ログインによって
  監査値や冪等性hashが変化しないようにした
- worker実行時にもgame参加権限とplayer seat所有を再検証し、queue待機中の権限失効を
  commandへ反映するようにした
- Supabase Data APIからゲーム関連tableへ到達できない境界を`anon`と
  `authenticated`の両roleに対する明示revokeで固定した
- CLIの認証sessionを原子的に保存し、POSIXのdirectoryとtoken fileを所有者限定権限へ
  固定した
- rate limit bucketの更新を原子的にし、並行要求でも設定上限を超えないようにした
- axeから色コントラスト除外とsidebar全体除外を取り除き、framework所有要素だけを
  最小限の例外として扱うようにした

## 第一段階から維持する判断

- `Game`を唯一の集約ルートとし、`submit()`と`advance()`へ状態変更を限定した
- `GameState`を不変スナップショット、遷移結果を型付きイベントへ統一した
- 未解決行動を`GameState`へ含め、`Game.restore(state, rules=...)`だけで復元できるようにした
- 行動、解決、フェーズ、勝敗、可視性をステートレスなポリシーへ分離した
- `domain/game`を`domain`直下へ展開し、`domain/llm`を削除した
- `usecase/jobs`と`usecase/internal`を廃止し、公開関数、DTO、portへ整理した
- LLMを`agents`、LangChain実装を`adapters/llm/langchain`へ分離した
- fake providerをLangChain標準`FakeListLLM`へ統一した
- `api`を`adapters`、`entrypoint`を`interfaces`へ変更した
- `commons`を`configuration`、`observability`、`security`へ分割した
- `backend`を廃止し、Python packageをトップレベルの`src`へ移した
- ポリシー構成、フェーズ順序、能力の開始日と対象条件を設定からdomainへ注入した
- 画面とLLMの対象候補計算を削除し、domainが返す合法対象へ統一した
- usecaseのテレメトリー出力を削除し、ログをinterfacesとadaptersへ限定した
- LLM provider設定とtrace sinkをusecaseから除外し、adapter側の`AgentRuntime`へ移した
- usecaseの公開面をcontext-first関数と直接利用するcommand、query、resultへ限定した
- 既定プリセットを定義順から選ぶ処理を廃止し、`game_default_setup_preset_id`から解決するようにした
- 役職、能力、シナリオ、ナレーション、プリセット間の参照を設定ロード時に検証するようにした
- 投票提出を非公開イベントに変更し、公開履歴には解決後の投票結果だけを残した
- 第一段階ではDBスキーマ、migration、Supabase保存方式を変更しなかった。第二段階では
  完全リプレイとAPI境界に必要なbaseline migrationへ置き換えた

## 配置

| Path | 責務 |
| --- | --- |
| `src/werewolf_agent/domain/` | 集約、状態、イベント、ポリシー、公開ゲームAPI |
| `src/werewolf_agent/application/` | `GameApplication`、内部handler、repository port |
| `src/werewolf_agent/agents/` | provider非依存の観測、意思決定、player port |
| `src/werewolf_agent/adapters/llm/langchain/` | LangChain、LangGraph、FakeListLLM |
| `src/werewolf_agent/adapters/` | GameClient、usecase bridge、外部サービスadapter |
| `src/werewolf_agent/adapters/agents/` | agentsとusecaseを接続するgame driver |
| `src/werewolf_agent/adapters/supabase/` | Auth、repository、operation、private trace sink |
| `src/werewolf_agent/api/` | FastAPIとHTTP composition root |
| `src/werewolf_agent/clients/` | CLI、Streamlit、非同期worker |
| `frontend/` | generated clientを使うReact本番UI |
| `src/werewolf_agent/settings/` | settings、TOML、resource検証 |
| `src/werewolf_agent/observability/` | loggingと実行context |
| `src/werewolf_agent/security/` | redaction |
| `src/werewolf_agent/contracts/` | 外部wire schemaと安全なerror |

## 設定

| 定義 | 既定ファイル | override |
| --- | --- | --- |
| ルールとポリシー構成 | `application/resources/game/rules.toml` | `WEREWOLF_GAME_RULES_FILE` |
| 役職と陣営 | `application/resources/game/roles.toml` | `WEREWOLF_GAME_ROLES_FILE` |
| 能力 | `application/resources/game/abilities.toml` | `WEREWOLF_GAME_ABILITIES_FILE` |
| 背景、表示名、説明 | `application/resources/presentation/catalog.toml` | `WEREWOLF_GAME_CATALOG_FILE` |
| 既定プリセット | `settings/resources/defaults.toml` | `WEREWOLF_GAME_DEFAULT_SETUP_PRESET_ID` |
| LLM players | `agents/resources/llm/players.toml` | `WEREWOLF_LLM_PLAYERS_FILE` |
| fake応答 | `agents/resources/llm/fake_responses.toml` | `WEREWOLF_LLM_FAKE_RESPONSES_FILE` |
| prompt | `agents/resources/prompts/agent_decision.toml` | `WEREWOLF_LLM_PROMPT_FILE` |

TOMLと環境変数は`configuration`だけが読みます。domainへは`RuleSetDefinition`、usecaseへは不変の`ApplicationContext`を注入します。

## 依存制約

- domainは他層へ依存しない
- usecaseはdomainと外部契約だけを使い、agentsとadaptersへ依存しない
- agentsはdomainとusecaseへ依存しない
- 自動プレイヤー接続は`adapters/agents/game_driver.py`だけに置く
- interfacesは`GameClient`経由で操作する
- domainとusecaseはlogging、DB、file I/Oを行わない
- 循環参照、import許可、外部ライブラリ配置、公開面は構造テストで固定する

## 実行コマンド

依存関係:

```bash
uv sync --group dev --extra worker --extra streamlit --extra llm
```

ローカルSupabaseとfake provider:

```bash
python -m scripts.supabase preflight
uv run --extra worker werewolf-agent-worker run
uv run werewolf-agent play --role-count werewolf=1 --role-count seer=1 --role-count knight=1 --role-count villager=3 --seed 1
```

Supabase worker:

```bash
python -m scripts.supabase preflight
uv run --extra worker werewolf-agent-worker run
```

Streamlit:

```bash
uv run --extra streamlit streamlit run src/werewolf_agent/clients/streamlit/app.py
```

全検証:

```bash
python -m scripts.quality quick
python -m scripts.quality check
python -m scripts.quality release
python -m scripts.quality deep --confirm-deep
python -m scripts.quality clean
```

pytest単体の既定levelは`quick`です。integration、monkey、benchmark、deepを意図せず
選択した場合は必要な`--test-level`を表示して実行を拒否します。品質reportは
成功結果は`.werewolf-agent/quality/latest`、非成功結果は
`.werewolf-agent/quality/failures`へ保存します。
品質runnerはFake LLMと事前取得済み依存だけを使用し、外部APIへ接続しません。

## 直近の検証結果

2026-07-25のDeep実測:

- Quick対象: 358件成功、level制限による12件skip
- Coverage対象: 359件成功、環境条件による1件skip
- Integration: 6件成功
- Deep: 4件成功
- React unit test: 21件成功
- Browser E2E: 15件成功、desktop対象外のmobile専用1件skip
- Coverage: 総合74.26%、line 79.32%、branch 49.03%
- Core benchmark: 平均0.236ms
- Ruff lint・format・docstring、mypy、Architecture、Prettier、TypeScript: 成功
- OpenAPI JSON・TypeScript生成型、Sphinx warning-as-error、wheel・sdist: 成功
- 隔離Supabase、API、worker、RLS、nonroot Docker runtime、外部通信遮断: 成功

最新値は`.werewolf-agent/quality/latest`の`report.json`と`summary.md`を正とします。

## 第一段階で削除した構造

- `domain/game`
- `domain/llm`
- `usecase/jobs`
- `usecase/internal`
- `api`
- `entrypoint`
- `commons`
- `backend`
- 旧FastAPI・Alembic起動スクリプト
- `GameService`
- `GameApi`
- 独自fake LLM
- 旧import aliasと互換export

## 将来候補

次の項目は現行要件の未達ではなく、別途要件化して扱う候補です。

- 実providerの長時間QAと評価基盤
- 複数manual player
- 追加役職
- private LLM traceの自動retention cleanup
- 登録済み以外の新しい集計、勝敗、可視性アルゴリズム

実providerのAPI keyを使わない通常検証でも、workerがSupabase Authの利用者区分を
再検証すること、fake gameが有料provider設定とsecretを継承しないこと、
失敗したcommandをrollbackしてから安全なProblem Detailsだけを保存することは
unit testで固定しています。

今回のゼロベースレビューでは、観戦専用game作成、完了gameの結果表示、文章上限の
API／DOM共通化、timelineの`limit`伝播、OpenAPIと実際のProblem Detailsの一致、
rate limiterのatomicity、axeの除外範囲、visual baseline更新手順、既存gameの
LLM mode固定、Supabase Data API権限、認証session保存、観戦画面のadmin reveal除去、
Docker testの独立性、API文書の既定非公開化、API応答のcache抑止、queue受理時の
LLM mode不変化、未使用public tableと旧public RPCの削除、host／Compose用DB DSNの
分離を追加で修正しました。
並列E2Eだけは同一Docker gateway IPを共有するためrate limitを1000へ上書きし、
production既定値120は変更していません。

## 次の一手

1. 実providerごとの契約テストを追加する
2. 設定組み合わせのproperty-based testを拡充する
3. 複数manual playerの権限モデルを設計する
4. 現行4役職とは独立した追加役職の要件を定義する
