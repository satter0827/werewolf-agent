(roadmap-1-0-0)=
# 1.0.0リリース計画

1.0.0は、設定可能な人狼ルールと外部Agentを決定的に実行し、固定条件で比較できる
headless Python SDKとself-hostedサービスを提供する。

domain、setup、Agent、Simulation、Experiment、application組み込み、API、worker、CLI、Streamlitの
実装済み構造は`docs/design`で定義する。この計画には正式リリースまで残っている判断と作業だけを置く。

## リリース候補

最初の公開候補を`1.0.0rc1`とする。RC以降は公開契約の不具合修正、文書修正、検証修正に限定し、
新しい機能、phase、action、互換形式を追加しない。

`1.0.0rc1`は次を同じrevisionで満たす。

- clean環境へwheelを導入し、公開Pythonモジュールと同梱snippetを実行できる。
- Composeと新規databaseからAPI、worker、CLI、Streamlitを起動できる。
- Coreと外部Rule Pack、組み込みと外部Agentが公開conformance契約を通る。
- 同じsetup、実装fingerprint、入力、seedからSimulationとExperimentを再生成できる。
- 公開状態、timeline、observation、revealの情報境界を自動検査できる。
- OpenAPI、Python API、setup、replay、Simulation、Experimentのversion関係が一致する。
- リリース、Deep、対応Python版、Supabase、ブラウザー、package、containerの品質証拠が揃う。

## 正式版

RCの利用結果から公開契約を変更する必要がないことを確認して`1.0.0`を作る。正式版はRCと同じ機能を
保持し、version、リリースノート、配布metadataだけを更新する。

PyPI、GHCR、GitHubリリースは同じcommitから生成し、product version、Git revision、artifact digestを
一致させる。署名、provenance、SBOM、OpenAPI、wheel、sdist、container imageをリリース成果物へ関連付ける。

## 判定

formatter、Ruff、mypy、対象テスト、Focus、Checkを通常変更の必須条件とする。RCはリリースとDeepを
fresh実行し、再利用した古い品質成果物だけで判定しない。

品質判定はFake、fixture、localhost、Compose内serviceだけで完結させる。有料provider、任意の外部API、
特定LLMの可用性や応答品質を必須条件にしない。ゲームバランスと会話品質は同じpreset、seed、役職割当、
熟考度で比較し、品質gateの成功と分離して記録する。

## 対象外

- 0.x setup、replay、保存データの互換移行
- 任意phaseと任意action type
- 任意コードを記述できるRule DSL
- 外部実装の自動探索
- 信頼できないpluginのsandbox実行
- 分散Experiment
- 自動prompt探索
- fine-tuningとreinforcement learning
- 標準LLM judge
- Experiment管理Web dashboard
- 外部frontendとmobile client
- 世界線とwhat-if UI
