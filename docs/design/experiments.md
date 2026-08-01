(experiments)=
# 反復Experiment

## 比較単位

Rule PackまたはAgentだけを条件差として分離し、同じseedと割当で比較可能なTrialを計画する。
実行、評価、reportは保存済みTrialを正本とし、中断再開後も同じ試行を重複させない。

## 条件

`RulesCondition`はsetup checksum、Rule Pack manifest、役職multiset、固定Agent仕様を保持する。
`AgentCondition`は同じ環境に加えてcontrollerとpersonaの組合せごとの`AgentSpec`を固定する。Agent比較ではsetup、
Rule Pack、役職multisetを全条件で一致させ、同時にルールを変える交絡を拒否する。
Rules比較では全条件のAgent仕様を一致させる。Rules条件とAgent条件は一つの`ExperimentSpec`へ
混在させない。

## Trial計画

`ExperimentSpec`はexperiment ID、比較条件、paired seed、seat ID、controller ID、persona IDを持つ。
各条件の`AgentBinding`はcontrollerとpersonaの直積を欠けなく定義する。personaはAgent Factoryの固定parameter
として`AgentSpec`のfingerprintに含め、Trialは実際のseatごとの`player_agent_specs`を保持する。
`plan_trials()`は同じseedとrotationの条件へ同じ`pair_id`を付ける。`trial_id`は条件、seed、割当、
setup checksum、Rule PackとAgentの実装fingerprintからSHA-256で生成する。実験仕様全体の
`experiment_fingerprint`はcondition、seed、割当候補、rotation方式を固定し、各TrialとReportへ記録する。

`balanced` rotationはプレイヤー数をnとしてseedごとにn²個の割当を作る。各controllerと役職、
各controllerとpersonaの組合せが同数になる。役職はTrialへ明示するため、Domainの乱数抽選へ
比較条件を委ねない。小規模な疎通確認では`none`を明示して一割当だけを使える。

```{image} ../_generated/architecture/experiment-pipeline.svg
:alt: ExperimentSpecからTrialを計画、実行、保存、評価してReportを作る流れ
:width: 100%
```

計画済みTrial IDと既存artifactのchecksumを先に照合し、不足したTrialだけをSimulationで実行する。
評価は完成したTrial artifactを入力とし、実行順や生成時刻に依存しないReportを作る。

## 境界

experimentsは複数試行と評価を所有し、一局の進行を再実装しない。各Trialは
`SimulationRunner`を使う。外部Rule Pack、Agent Factory、persona、artifact storeは利用者または
composition rootが明示注入し、設定値から任意モジュールをimportしない。

`TrialSessionFactory`は計画へ対応する未実行`SimulationSession`を返す。`TrialRunner`は既存の
Trial artifactを先に検証し、未完了分だけを計画順に実行する。`max_new_trials`は一回の実行量を
制限し、残りのTrial IDを返す。例外またはプロセス停止で完成しなかったTrialは保存せず、次回に
同じIDで再実行する。

`TrialArtifactStore`は`.werewolf-agent/experiments/<experiment-id>/experiment.json`へIDと仕様fingerprintの
immutableなbindingを保存し、同じIDへ異なる仕様を混在させない。`trials/`へtrial単位のJSONを
保存する。artifactはplan、最終状態、step、event、chain-of-thoughtを含まないdecision traceを持つ。
checksumを検証し、一時fileのflush後に新規pathへatomic publishする。既存artifactとplanが一致しない場合は
再実行せず失敗する。

Runnerは実行前にSessionのsimulation ID、seed、Rule Pack manifest、プレイヤー、明示役職、seatごとのAgent specを
Trial planと照合する。Factoryが異なる実装を返した場合はSessionをcloseし、artifactを保存しない。

実時間、token、費用は運用観測値として保存できるが、Trial IDと決定性の判定へ含めない。
LLM judgeは標準評価に使わず、説得や欺瞞の観測値を因果効果として断定しない。

`StandardEvaluator`は条件ごとに合法判断率、fallback率、陣営別勝率、identity faction別生存率、
controller別・役職別の勝率と生存率、投票対象、能力対象、latency、token、費用を集計する。
勝率の分母には`SimulationStopReason.FINISHED`のTrialだけを含め、上限到達やcancelによる未完了Trialは
`incomplete_trial_count`として分離する。生存率は停止時点の運用観測値として全Trialを対象にする。
対象分布はプレイヤーIDに加えてtargetのidentity factionでも集計する。合法判断率はfallbackへ移る前にAgent応答が
そのまま採用された割合とする。belief校正を有効にした場合は、Agentが返した各プレイヤーの
werewolf確率と最終的なidentity factionからBrier scoreを計算する。
tokenと費用は計測値があるdecisionだけを合計し、sample数を併記して未計測と実測0を分離する。

外部`Evaluator`は安定ID、意味論version、有限なJSON互換metricを返す。`build_report()`はTrialを
ID順に並べ、`ExperimentSpec`由来の全condition IDを`expected_condition_ids`として受け取る。条件別評価、
全条件が揃うpaired Trial数、Trial内容の`source_checksum`を生成する。
生成時刻や実行環境をReportへ含めず、同じartifact集合から同じJSONを得る。

## 検証

契約テストは条件分離、paired ID、実装fingerprint、決定的計画を確認する。rotationテストは
controllerと役職、controllerとpersonaの割当回数が均衡することを確認する。
