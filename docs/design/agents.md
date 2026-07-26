(agents)=
# Agent と自動進行

agents 層は player が観測できる情報から意思決定を作る。ゲーム状態の変更やルール
判定は行わず、provider 固有処理とゲーム進行を分離する。

## 観測と意思決定

観測には、その player の公開情報と本人だけが知り得る情報だけを含める。他 player
の役職、未公開の夜行動、運用上の秘密情報を prompt に渡さない。

LLM の自由文は直接ゲーム操作へ変換しない。構造化出力を Pydantic または
JSON Schema 相当で検証し、利用可能な action と対象を確認してから domain 操作へ
渡す。失敗時の再試行回数や fallback は設定値で制御する。

## Provider 境界

`werewolf_agent.agents` は観測、意思決定、trace、player port を定義する。
`adapters.llm.langchain`は単一のLangGraph、prompt、provider、Fake chat modelを実装する。
外部 API を使わない再現可能な fixture を通常のテスト経路とする。

標準graphは観測の正規化、必須action、role hint、target評価、prompt、model呼出し、
構造化出力検証、修復、決定的fallbackを順に処理する。graph topologyとrevisionは
adapter codeが所有し、game作成contractや保存状態から選択しない。tool、memory、分岐は
必要になった時点でnodeまたはsubgraphとして追加する。

## Game driver

`adapters/agents/game_driver.py`がapplicationとagentsを接続する唯一の変換点である。
公開状態を observation に変換し、decision を application action に変換する。
agentsはdomainとapplicationに依存せず、applicationもagentsに依存しない。

## Worker

worker はPGMQの`game_operations`を取得し、認可された game を自動進行する。
LangGraph実行前後だけ短いtransactionを開き、model待機中はDB connectionを保持しない。
visibility timeoutは別connectionで更新する。processが中断したmessageはPGMQが再配送し、
捕捉した実行エラーは分類に従って再配送またはsafe Problem Details付きの`failed`へ確定する。有料 provider は
認証済み利用者の game に限定し、provider の選択と model は設定から解決する。

private LLM trace は公開 timeline から分離して保存し、入力前と記録前の両方で秘密
情報を除去する。provider生応答と修復後payloadを別fieldで保持し、schema検証結果、修復回数、
fallback、provider error、token usage、文字数、byte数、latencyを正規化して記録する。
providerがusageを返さない場合はtoken数を推計しない。
