(build-release)=
# ビルドとリリース

同じcommit、lock file、設定から再現できる成果物を作る。build中に依存解決や
外部API呼び出しを行わず、準備と検証を分離する。

## 入力

- version管理されたソースコード、設定デフォルト、resource
- `uv.lock`
- buildに必要なtoolchainと事前取得済みimage
- リリース環境から注入されるcredential

credential、local `.env`、cache、品質reportは配布物へ含めない。

## 手順

1. `develop`から`main`へのPRであることを確認する。
2. lock file、FastAPIから生成したOpenAPI、checked-in `contracts/openapi.json`が一致することを確認する。
3. PRのテスト用merge commitに対してDeepと対応Python版の互換性検査を実行する。
4. Python packageとcontainer imageを同じrevisionから作る。
5. migrationを対象環境へ適用できることを検証する。
6. artifactのversion、digest、検証reportを関連付ける。
7. 承認された配布基盤がartifactを配置し、起動時検証を行う。

## Version契約

product versionの正本は`src/werewolf_agent/_version.py`とし、mainへmergeしたリリースを基準に
SemVerで更新する。setup文書、replay、public event、architecture成果物、quality evidenceは
独立した互換性境界として個別のSemVerを持つ。HTTP pathの`/api/v1`はroute majorであり、
配布versionや設定値として扱わない。

`scripts.versioning`は所有モジュールと監視pathを`registry.toml`から読み、SemVerの形式、退行、
所有範囲の変更に対するversion更新漏れを検査する。初回`0.1.0`では新しい正本をbaselineとして
確立し、以後はmain上の値と比較する。

Supabaseの`0.1.0` migrationは新規databaseを構築する単一baselineである。リリース前databaseの
data移行やmigration history修復は行わない。既存環境を切り替える場合は、main merge後にbackupと
reset対象を明示し、別の承認された運用として実施する。

## Versionと契約

破壊的変更を許容する開発方針でも、同じ配布物内のAPI、OpenAPI contract、
database schemaは一致させる。旧schemaの無期限な読み替えは設けず、必要な
migrationと切替条件をリリース単位で定義する。

## 失敗時

build、テスト、migration、起動確認のいずれかが失敗したartifactは公開しない。
再実行は同じ入力から新しいreportを作り、失敗結果を上書きして成功扱いしない。
