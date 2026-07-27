# Documentation

`design`は決定済み仕様、`notes`は非規範的な調査記録です。

- designは目的、責務、境界、検証の粒度で記述する。
- 同じ仕様を複数の章で定義しない。
- 時点や編集経緯をdesign本文へ含めない。
- 実装で保証できる構造はテストへ置き、判断原則だけを文書へ置く。
- default、環境変数、CLI surface、OpenAPI、品質成果物は所有するsourceを正本とする。
- 実測件数、最新結果、生成画像をsource文書へ固定しない。
- 調査結果が仕様になった場合はdesignへ移し、役目を終えたnotesとassetを削除する。
