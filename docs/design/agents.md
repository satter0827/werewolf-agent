(agents)=
# エージェントと自動進行

agents層はプレイヤーが観測できる情報から意思決定を作る。ゲーム状態の変更やルール
判定は行わず、provider固有処理とゲーム進行を分離する。

## 観測と意思決定

観測には、そのプレイヤーの公開情報と本人だけが知り得る情報だけを含める。他プレイヤー
の役職、未公開の夜行動、運用上の秘密情報をpromptに渡さない。

LLMの自由文は直接ゲーム操作へ変換しない。生JSONをPydantic schemaで検証し、
利用可能なaction、対象、発言対象、公開evidenceを確認してからdomain操作へ渡す。
意味を変えない正規化は完全なMarkdown fenceの除去だけとする。不正応答は書き換えず、
再問い合わせを行わず、決定的fallbackへ送る。

## Agent SDK契約

`werewolf_agent.agents`は標準ライブラリだけで`AgentFactory`、`AgentSession`、`AgentContext`、
`AgentSpec`、`AgentObservation`、`DecisionRequest`、`DecisionResponse`、`DecisionTrace`を公開する。
Factoryはgameとプレイヤーごとに新しいSessionを生成し、Sessionは同期`decide()`と冪等な`close()`だけを
提供する。timeoutとcancelは呼出し側のSimulationまたはアダプターが管理する。

Requestは本人用observation、公開timeline、合法action、合法target、timezone付きdeadline、
decision seedだけを保持する。完全state、application service、リポジトリ、provider credentialは
含めない。Responseのbelief、confidence、intent、metadataは任意であり、chain-of-thoughtを要求または
保存しない。Agent identityはimplementation version、SHA-256 fingerprint、固定parameterで記録する。

## LLMプロバイダー境界

`agents.models`と`agents.ports`は既存LLM pipelineの内部DTOを所有する。`adapters.llm`は
LangChain型への変換とFake fixtureを所有する。providerはcomposition rootで一度だけ選び、その後はFakeと実LLMが
同じchat request、応答正規化、schema検証、合法手検証、fallbackを通る。

意思決定は`観測正規化 → context構築 → model呼出し → JSON正規化 → schema・合法手検証
→ fallback → trace`の明示的なpipelineである。LLM自身が利用可能なactionと合法対象から
一つを選ぶ。完全なactionが一意で発言や対象を必要としない場合だけmodel呼出しを省略する。
`quick`、`standard`、`deep`は参照event上限と最大出力だけを変え、呼出しは一回に固定する。
発言の`focus_id`と`evidence_id`は公開発言記録へ保存し、次の発言・投票で本人を含む全プレイヤーが
同じ公開立場を参照する。これによりエージェント固有の非公開memoryを追加せず、発言変更と投票整合を
公開情報だけで評価する。

## ゲーム進行アダプター

`adapters/agents/game_driver.py`がapplicationとagentsを接続する唯一の変換点である。
公開状態をobservationに変換し、decisionをapplication actionに変換する。
agentsはdomainとapplicationに依存せず、applicationもagentsに依存しない。

## worker

workerはPGMQの`game_operations`を取得し、認可されたgameを自動進行する。
エージェント処理の実行前後だけ短いtransactionを開き、model待機中はDB connectionを保持しない。
visibility timeoutは別connectionで更新する。プロセスが中断したmessageはPGMQが再配送し、
捕捉した実行エラーは分類に従って再配送またはsafe Problem Details付きの`failed`へ確定する。有料providerは
認証済み利用者のgameに限定し、providerの選択とmodelは設定から解決する。

private LLM traceは公開timelineから分離して保存する。本人に認可されたobservationとprompt、
provider生応答、検証済みdecision、正規化、schema・合法手検証、fallback、provider error、
token usage、文字数、byte数、latencyを記録する。providerがusageを返さない場合はtoken数を
推計しない。
