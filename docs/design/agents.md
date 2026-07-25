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

`werewolf_agent.agents` は観測、意思決定、player port を定義する。
`adapters.llm.langchain`はLangChain graph、prompt、provider、FakeListLLMを実装する。
外部 API を使わない再現可能な fixture を通常のテスト経路とする。

## Game driver

`adapters/agents/game_driver.py`がapplicationとagentsを接続する唯一の変換点である。
公開状態を observation に変換し、decision を application action に変換する。
agentsはdomainとapplicationに依存せず、applicationもagentsに依存しない。

## Worker

worker は operation queue を取得し、認可された game を自動進行する。処理単位ごとに
実行 context を作る。lease 中に process が中断した operation は再取得し、捕捉した
実行エラーは safe Problem Details とともに `failed` へ確定する。有料 provider は
認証済み利用者の game に限定し、provider の選択と model は設定から解決する。

private LLM trace は公開 timeline から分離して保存し、入力前と記録前の両方で秘密
情報を除去する。
