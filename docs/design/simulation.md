(simulation)=
# 単一ゲームSimulation

## 目的

Notebook、worker、実験から同じ一局実行契約を利用し、Agent差し替え後もdomainの決定性と
本人用observationの秘匿性を維持する。

## 契約

- `SimulationSpec`はsimulation ID、game ID、seed、プレイヤー別controller、実行上限を固定する。
- `PlayerController`はmanualまたは外部注入した`AgentFactory`を一人へ割り当てる。
- `SimulationRunner.create()`と`restore()`は同じseed規則でGameを開始する。
- `SimulationSession.step()`は一つのaction、phase進行、停止判定のいずれかを返す。
- `submit_manual()`はmanual controllerのactionだけを`Game`へ渡す。
- `run()`は終局、手動入力待ち、action/phase上限、cancelのいずれかで停止する。
- Agent sessionはゲームとプレイヤーごとに一つ作り、終了時にまとめてcloseする。

## 境界

simulationは`Game.view_for()`からAgent入力を構築し、完全状態をAgentへ渡さない。
状態変更は`Game.submit()`と`Game.advance()`だけが行う。simulationはリポジトリ、queue、HTTP、
provider設定、複数試行、統計、checkpoint、artifactを所有しない。これらはapplication、worker、
実験runnerなど外側のcomposition rootが組み立てる。

同期の既定executorはAgentを一回だけ呼び出し、応答後にtimeout超過を検出する。実行中の処理を
安全に強制停止する必要があるproviderは、プロセスまたはprovider固有timeoutを使う外部executorを
注入する。simulationは停止不能なthreadを生成しない。

## 決定性

role assignment、phase進行、プレイヤーsession、decisionごとのseedをnamespaceで分離する。
同じsetup、rule pack、controller仕様、入力、seedからstate、domain event、action/response列を再現する。
実時間から得るlatencyは診断情報であり、再現性の比較対象に含めない。標準runnerはwall clockを
`DecisionRequest`へ含めない。

## 検証

単体テストは同一seedの再現性、manual待機と再開、Agent失敗時fallback、上限、cancel、controller整合を
確認する。構造テストはsimulationが標準library、agents、domain、setup以外へ依存しないことを確認する。
