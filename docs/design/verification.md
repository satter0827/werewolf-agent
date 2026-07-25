(verification)=
# 検証

## 目的

製品の合否をrepository内のsource、test、fixture、local process、Compose serviceから
判定する。package取得先や有料providerの可用性を製品品質と混同しない。

## 品質profile

| Profile | 責務 |
| --- | --- |
| `quick` | architecture、静的検査、unit |
| `check` | 決定的な全検査、docs、contract、build |
| `release` | Supabase、API、worker、browser、container |
| `deep` | 長時間test、fault injection、benchmark |

```powershell
uv run --no-sync python -m scripts.quality quick
uv run --no-sync python -m scripts.quality check
uv run --no-sync python -m scripts.quality release
uv run --no-sync python -m scripts.quality deep --confirm-deep
uv run --no-sync python -m scripts.quality gate python-static
uv run --no-sync python -m scripts.quality list
uv run --no-sync python -m scripts.quality clean
```

## 外部接続境界

品質processからprovider credentialと外部base URLを除去し、fake providerとtelemetry
無効化を強制する。Python test、Playwright、E2E containerは非loopback通信を拒否する。
依存取得は`scripts.environment`、外部情報を使う監査は`Dependencies: Audit`へ分離する。

## 判定

- `passed`: 検査を満たす。
- `failed`: assertion、lint、型、契約に違反する。
- `blocked`: tool、権限、Docker、local serviceなどの実行条件が不足する。
- `error`: runnerまたは検査基盤が異常終了する。
- `skipped`: 依存gateが完了していない。

## 構造と成果物

architecture testは`scripts/architecture/rules.toml`からroot、layer、path規則、framework、
公開面を検査する。report、log、coverage、browser成果物は`.werewolf-agent`へ保存し、
scratchは`.werewolf-agent/runtime/tmp`へ置く。
