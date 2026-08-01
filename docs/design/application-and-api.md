(application-api)=
# アプリケーションとAPI

applicationは利用者の要求をdomain操作へ変換し、保存と公開DTOの生成を調整する。
HTTP APIは認証、wire schema、エラー応答を受け持つ。ユースケースごとの認可はapplicationが
`AccessPolicy`を通じて完結させる。

## アプリケーション境界

Python利用者向けの公開面は`werewolf_agent.domain`と`werewolf_agent.application`の
`__all__`で定義する。公開署名から到達するproject内の型と、利用者が捕捉する例外は同じfacadeから
importできる。HTTP request schemaと内部handlerは公開Python APIに含めない。
`Actor`と例外変換はGame・Setup両facadeが共有するapplication所有境界とし、peer facade間で所有しない。
handlerはリポジトリportから集約を読み、domainの操作を呼び、結果を保存して
公開DTOへ射影する。application自身はログやtelemetryを出力しない。
作成要求のseedは公開roster生成だけに使用する。applicationはprivate strategy、役職割当、ゲーム進行に
使う非公開runtime seedを独立して生成し、コマンド記録とprivate snapshotへ保存する。公開結果と状態には
runtime seedを含めず、以後のdomain処理は暗黙の乱数源を使用しない。

リポジトリportは保存先の技術を規定しない。in-memory実装とSupabase実装は同じ
契約に従い、applicationからdatabase SDKやSQLを隠す。
`GameApplication`は一つの更新で行うsnapshot取得、domain操作、状態保存、event追加を
`GameRepository.transaction()`の内側で実行する。in-memory実装はプロセス内lock、Supabase実装は
database transactionへ対応付け、複数methodにまたがる更新と公開timelineのversionを分離しない。
game一覧はfacadeが受け取った`Actor.user_id`をqueryへ固定し、リポジトリportが参加関係を
検索条件として適用する。request-scopedアダプターの暗黙状態だけに認可主体を依存させない。

## 組み込み境界

`create_embedded_application()`は`GameApplication`、`SetupApplication`、固定`Actor`、
`InlineCommandExecutor`を一つのbundleとして返す。既定ではin-memoryリポジトリと
`SingleTenantAccessPolicy`を使用し、状態をモジュールglobalへ保存しない。同じリポジトリを別のfactoryへ
注入した場合だけ状態を共有する。外部リポジトリとRule Packは同じportへ明示注入する。
外部gameリポジトリはtenant境界を推測できないため、対応する`AccessPolicy`も必須とする。
既定の`SingleTenantAccessPolicy`はfactoryが生成した専用in-memoryリポジトリだけへ適用する。
外部リポジトリの保存対象tenantと`AccessPolicy`の利用者はcomposition rootが一致させる。

Factoryは環境変数、HTTP、database、worker、package resourceを読み込まない。利用者は
`GameApplicationConfig`と`SetupTemplateCatalog`を実験条件として渡す。Inline実行でも認可、
期待version、transaction、公開resultの境界は通常の`GameApplication`と同じである。
固定`Actor`は既定では通常利用者とする。完全状態を必要とする信頼済みの単一Pythonプロセスだけが
`allow_reveal=True`を明示してadmin境界を有効化する。複数利用者を隔離する用途にはHTTP APIと
永続リポジトリを使用する。

## HTTP API

FastAPIはapplication composition rootとして、設定、リポジトリ、認証アダプター、
`GameApplication`を組み立てる。APIは次を保証する。

- bearer tokenを検証し、操作主体を`Actor`へ変換する。
- 認証済みprincipalを`Actor`へ変換する。
- Pydantic契約で入力と出力を検証する。
- 安全な例外だけをProblem Detailsへ変換する。
- stack traceとtokenを応答へ含めず、private stateを通常応答へ含めない。
- 本人observationは型付きwire schemaへallowlist投影し、合法行動ごとの安定key、能力ID、
  合法対象ID、message要否を返す。Domain内部の理由、非公開履歴、勝利プレイヤーIDは返さない。

API routeは`werewolf_agent.application`の公開facadeだけをimportする。内部handler、model、port、
errorモジュールへの直接依存は構造テストで拒否する。

CORSはAPIの一般的な外部境界として扱う。既定では無効とし、許可originを設定した場合だけ
middlewareを有効にする。設定fieldと環境変数名はsettings modelと`.env.example`を正本とする。

完全状態を返すrevealは通常のgame routeと`GameClient` portから分離する。管理者
認可と`reveal_api_enabled`の両方を満たす専用routeだけがreveal DTOを返す。
整合性、operation、LLM利用量の診断APIはprivate payloadを返さない。

## 操作の流れ

1. クライアントがchecked-in OpenAPI contractに従ってHTTP要求を送る。
2. APIが認証と入力検証を行う。
3. `GameApplication`が認可し、集約を取得してdomain操作を呼ぶ。
4. リポジトリが更新後の完全状態を保存する。
5. projectionが閲覧者向けの公開DTOを作る。
6. APIが公開応答を返し、外部境界で観測情報を記録する。

同一操作の再送、競合、存在しないgame、許可されない操作は、domainエラーと
infrastructureエラーを混同せず、安定したerror codeで表す。

公開Python serviceは認可拒否を`AUTHORIZATION_FAILED`、resource不存在を
`RESOURCE_NOT_FOUND`、portの構成不足を`ConfigError`、ゲーム操作違反を`GameError`系で表す。
入力modelとdomain値の構築時検証は`ValueError`で表す。
Portや内部処理の`PermissionError`は認可エラーへ変換し、その他の予期しない例外は原因を保持した
`InternalError`へ変換する。APIは内部障害の原因をログへ記録するが、応答には公開しない。

## worker

workerはqueue取得、operation dispatch、transaction lifecycle、完了時の観測だけを
調整する。PGMQ操作、参加者確認、完了・失敗記録、private view materializeのSQLは
`SupabaseWorkerStore`が所有する。自動進行は準備、DB外計算、version付きcommitへ分け、
古い計算結果を保存しない。commitもapplication facadeがactorを認可してから保存する。
DB外計算ではworkerがAgent runtimeを構築し、Simulationがaction適用とphase進行を一度だけ行う。
applicationはtransition完了済みのGameから保存用projectionを作り、phaseを重ねて進めない。
APIとworkerはプロセス所有poolからconnectionを借用する。workerはqueue処理全体のtransactionを
所有し、`GameApplication`の更新単位はリポジトリが同じconnection上のtransactionへ対応付ける。

`ApplicationContext`は`RulePackRegistry`を必須依存として受け取り、組み込みRule Packを暗黙登録しない。
APIは`create_app(rule_packs=...)`、組み込みapplicationは`create_embedded_application(rule_packs=...)`、
workerは`WorkerDependencies`から同じ契約を注入する。通常起動は
`create_core_rule_policy_registry()`をcomposition rootで明示的に選ぶ。workerへ注入する
`agent_factories`はプレイヤーIDをkeyとし、指定したseatだけ既定のLangChain factoryを置き換える。
設定値からimport pathを解決せず、呼出側が構築済みの信頼済みobjectだけを渡す。

## 契約の管理

外部契約は`werewolf_agent.contracts`に置き、`contracts/openapi.json`を正本とする。
FastAPIから生成したschemaを`contracts/openapi.json`と比較し、差分を契約gateで拒否する。
CLIとStreamlitは`GameClient` portと
public wire schemaを使い、domainやリポジトリを直接importしない。
winnerと公開factionは`village`、`werewolf`、`fox`の正規IDを使い、clientだけの別名を持たない。
