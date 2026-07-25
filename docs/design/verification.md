(verification)=
# 検証

検証は速い局所確認から、外部依存を含む release 確認へ段階化する。すべての品質
profile は `scripts.quality` が調整し、個々の検査は独立したコマンドとしても動く。

## 基本検証

```powershell
uv run --no-sync ruff format --check .
uv run --no-sync ruff check --no-cache .
uv run --no-sync mypy --no-incremental src
uv run --no-sync pytest
```

docstring は Ruff の Google convention と、公開 API の構造検査で保証する。
短い関数へ定型文を強制せず、公開される module、class、function、method の説明と
引数、戻り値、例外の実態をコードと一致させる。

## 品質 profile

| profile | 用途 | 主な検査 |
| --- | --- | --- |
| `quick` | 編集中の高速確認 | architecture、静的検査、主要 unit test |
| `check` | 通常の変更確認 | 全 unit test、型、docs、frontend |
| `release` | 配布前確認 | build、migration、container、契約 |
| `deep` | 定期的な広範囲確認 | release に加えて長時間 QA と監査 |

```powershell
uv run --no-sync python -m scripts.quality quick
uv run --no-sync python -m scripts.quality check
uv run --no-sync python -m scripts.quality gate python-static
uv run --no-sync python -m scripts.quality list
```

quality runner は gate の順序、timeout、report、artifact freshness を管理する。
docs 固有の検査や Sphinx 呼び出しは `scripts.docs` が所有し、quality runner は
その公開コマンドを呼ぶだけにする。

## 構造検証

architecture test は layer 間の import、cycle、例外 path を検査する。
`scripts.architecture` は同じ規則から JSON、schema、評価文書、SVG を生成する。
docs test は必須 lifecycle、toctree 到達性、公開 automodule、禁止した docstring
抑制だけを検査し、章数や文章量を固定しない。

## 成果物

共有する検証結果は `.werewolf-agent` に置く。cache と配布物を source tree に
混在させず、report から実行コマンド、終了状態、所要時間、artifact path を追跡する。
