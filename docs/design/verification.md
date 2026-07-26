(verification)=
# 検証

## 目的

製品の合否をrepository内のsource、test、fixture、local process、Compose serviceから
判定する。package取得先や有料providerの可用性を製品品質と混同しない。

## 品質profile

| Profile | 責務 |
| --- | --- |
| `quick` | architecture、format、lint、型、unit、軽量Hypothesis |
| `check` | Quick、offline test、coverage観測、docs、OpenAPI、Schemathesis、build |
| `release` | Check、Supabase、API、worker、clients、browser、package、container |
| `deep` | 長時間stateful、fault injection、性能観測 |
| `review` | UI、Gameplay、Local LLMの読解用証拠。合否には含めない |

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
利用者が運用設定として有料providerを選ぶことは許可するが、そのcredential、応答、
可用性を品質判定やreviewの前提にしない。Local LLM reviewはloopbackだけを許可する。

## 判定

- `passed`: 検査を満たす。
- `failed`: assertion、lint、型、契約に違反する。
- `blocked`: tool、権限、Docker、local serviceなどの実行条件が不足する。
- `error`: runnerまたは検査基盤が異常終了する。
- `skipped`: 依存gateが完了していない。

## 構造と成果物

architecture testは`scripts/architecture/rules.toml`を正本とし、grimpのimport graphから
間接依存と循環を検査する。Hypothesisはdomain操作列の生成と縮小、Schemathesisは
OpenAPIのpositive/negative入力とDeepのstateful操作列、respxはHTTP異常、psutilは
子processと実行中runの所有権を担当する。
構造testはdomainの第三者package、applicationからwire contractへの依存、API routeから
access/queue adapterへの直接呼出し、公開export allowlist、旧plural faction IDを検出する。
replay testはcommand、event、state、projection、rule snapshotの改変と旧形式を、最初の
不一致versionで検出する。必須fieldが欠けた破損記録も例外を公開せずunsupportedとして扱う。
domain testは復元snapshotのplayer数、役職構成、終局結果、pending action参照の不整合を拒否する。

各runは`report.json`、`summary.md`、`events.jsonl`、`manifest.json`を持つ。manifestには
producer、分類、MIME、size、SHA-256、保持状態を記録する。成功runもlog、JSON/HTMLの
test結果、coverage、画面を含む一式でlatestを置換する。失敗runは成功済みgateの証拠も
保持し、削除可能なのは再生成可能な動画などに限る。必須証拠が容量上限を超えた場合は
削除せず成果物契約違反にする。完了記録のないrunは次回起動時にfailureへ回収する。

Playwrightは操作、contract、accessibility、console、外部通信を判定する。見た目はpixel
差分で合否を出さず、setup、進行中、観戦、空の履歴、完了結果を含むdesktop/mobileの
個別画像、一覧画像、HTML/JSONを人が読む。
coverage、benchmark、面白さ、会話品質にも根拠のない閾値を置かず、観測値と証拠を残す。
Gameplay reviewは現在のrules、roles、abilitiesからseed固定で一局を完走し、設定、操作列、
公開timeline、終局を保存する。解決前の行動対象などprivate情報はreview証拠へ保存しない。
Local LLM reviewは`WEREWOLF_LOCAL_LLM_BASE_URL`と`WEREWOLF_LOCAL_LLM_MODEL`を使い、
base URLがloopbackである場合だけOpenAI互換`/chat/completions`の会話を保存する。
