(build-release)=
# ビルドとリリース

同じ commit、lock file、設定から再現できる成果物を作る。build 中に依存解決や
外部 API 呼び出しを行わず、準備と検証を分離する。

## 入力

- version 管理された source、設定 default、resource
- `uv.lock` と frontend lock file
- build に必要な toolchain と事前取得済み image
- release 環境から注入される credential

credential、local `.env`、cache、品質 report は配布物へ含めない。

## 手順

1. lock file と generated OpenAPI client に差分がないことを確認する。
2. `uv run --no-sync python -m scripts.quality release` を実行する。
3. Python package、frontend、container image を同じ revision から作る。
4. migration を対象環境へ適用できることを検証する。
5. artifact の version、digest、検証 report を関連付ける。
6. 承認された配布基盤が artifact を配置し、起動時検証を行う。

## Version と契約

破壊的変更を許容する開発方針でも、同じ配布物内の API、generated client、
database schema は一致させる。旧 schema の無期限な読み替えは設けず、必要な
migration と切替条件を release 単位で定義する。

## 失敗時

build、test、migration、起動確認のいずれかが失敗した artifact は公開しない。
再実行は同じ入力から新しい report を作り、失敗結果を上書きして成功扱いしない。
