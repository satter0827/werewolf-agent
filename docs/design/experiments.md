(experiments)=
# 反復Experiment

## 目的

Rule PackまたはAgentだけを条件差として分離し、同じseedと割当で比較可能なTrialを計画する。
実行、評価、reportは保存済みTrialを正本とし、中断再開後も同じ試行を重複させない。

## 条件

`RulesCondition`はsetup checksum、Rule Pack manifest、役職multisetを固定する。
`AgentCondition`は同じ環境に加えてcontrollerごとの`AgentSpec`を固定する。Agent比較ではsetup、
Rule Pack、役職multisetを全条件で一致させ、同時にルールを変える交絡を拒否する。
Rules条件とAgent条件は一つの`ExperimentSpec`へ混在させない。

## Trial計画

`ExperimentSpec`はexperiment ID、比較条件、paired seed、seat ID、controller ID、persona IDを持つ。
`plan_trials()`は同じseedとrotationの条件へ同じ`pair_id`を付ける。`trial_id`は条件、seed、割当、
setup checksum、Rule PackとAgentの実装fingerprintからSHA-256で生成する。

`balanced` rotationはプレイヤー数をnとしてseedごとにn²個の割当を作る。各controllerと役職、
各controllerとpersonaの組合せが同数になる。役職はTrialへ明示するため、Domainの乱数抽選へ
比較条件を委ねない。小規模な疎通確認では`none`を明示して一割当だけを使える。

## 境界

experimentsは複数試行と評価を所有し、一局の進行を再実装しない。各Trialは
`SimulationRunner`を使う。外部Rule Pack、Agent Factory、persona、artifact storeは利用者または
composition rootが明示注入し、設定値から任意モジュールをimportしない。

実時間、token、費用は運用観測値として保存できるが、Trial IDと決定性の判定へ含めない。
LLM judgeは標準評価に使わず、説得や欺瞞の観測値を因果効果として断定しない。

## 検証

契約テストは条件分離、paired ID、実装fingerprint、決定的計画を確認する。rotationテストは
controllerと役職、controllerとpersonaの割当回数が均衡することを確認する。
