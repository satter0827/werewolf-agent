(runtime-configuration-reference)=
# 実行時設定

設定は `werewolf_agent.configuration` が起動時に読み込み、型、範囲、相互参照を検証
する。具体的な環境変数名と default は `.env.example` と settings model を正とする。

## 設定領域

| 領域 | 内容 | 秘密情報 |
| --- | --- | --- |
| application | environment、host、port、公開 URL | なし |
| database | Supabase URL、schema、接続 timeout | service key |
| authentication | issuer、audience、token 検証 | signing material |
| worker | polling、lease、retry、同時実行数 | なし |
| LLM | provider、model、timeout、構造化出力 | API key |
| observability | level、format、sink、trace | sink credential |
| game | role、rule policy、制限値 | なし |

秘密値は `.env.example` に実値を記載しない。設定値をログへ出す場合は redaction 後の
safe representation を使う。

## 検証

```powershell
uv run werewolf-agent doctor
```

doctor は設定と packaged resource を検証する。database や provider への外部接続を
伴う確認は個別の preflight として実行する。

## 設定追加

設定を追加する場合は settings model、安全な default、`.env.example`、利用箇所、
検証 test、設計書を同じ変更で更新する。同じ意味の環境変数 alias や暗黙 fallback
は追加しない。
