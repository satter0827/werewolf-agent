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

product versionの正本は`src/werewolf_agent/_version.py`とし、Python distributionの標準である
PEP 440で表す。mainへmergeしたリリースを比較基準にする。setup文書、replay、public event、
architecture成果物、quality evidenceは独立した互換性境界としてSemVer 2.0.0を持つ。
安定版では`major`を破壊的変更、`minor`を互換性のある機能追加、`patch`を互換性のある修正に使う。
`0.x`から`1.0.0`への更新は安定版の宣言を伴うため、自動提案だけで決定しない。HTTP pathの
`/api/v1`はroute majorであり、配布versionや設定値として扱わない。

`scripts.versioning`は所有モジュール、規格、監視pathを`registry.toml`から読む。`suggest`は
Conventional Commitから変更levelを提案するだけでversionを変更しない。利用者がlevelを指定する
`bump`はmainとの差分とworking treeから対象境界を選び、productと必要な境界だけを同じlevelで
更新する。`check`は規格、退行、precedenceを変えないmetadata更新、所有範囲の変更に対する
version更新漏れを検査する。初回`0.1.0`では新しい正本をbaselineとして確立し、以後はmain上の
値と比較する。mainへmergeした後にversionを変更する処理は設けず、検証対象とmerge結果を一致させる。

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
