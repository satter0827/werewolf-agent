(runtime-configuration-reference)=
# 実行時設定

設定は`werewolf_agent.settings`が起動時に読み込み、型、範囲、相互参照を検証する。
具体的なfieldとdefaultは`src/werewolf_agent/settings/sections`と
`src/werewolf_agent/settings/resources/defaults.toml`、環境変数の利用例は`.env.example`を
正とする。このページには値を複製せず、設定領域と変更時の契約だけを示す。

## 設定領域

| 領域 | 内容 | 秘密情報 |
| --- | --- | --- |
| application | environment、host、port、公開 URL | なし |
| database | Supabase URL、schema、接続 timeout | service key |
| authentication | issuer、audience、token 検証 | signing material |
| worker | polling、lease、retry、同時実行数 | なし |
| LLM | provider、model、timeout、構造化出力 | API key |
| observability | level、format、sink、trace | sink credential |
| game | default template、narration、player数制限 | なし |

ゲームごとのmechanics、theme、player generationはruntime設定ではなく
`GameSetupDocument`が所有する。同梱templateとcatalogは
`src/werewolf_agent/application/resources/setups`を正本とする。

秘密値は `.env.example` に実値を記載しない。設定値をログへ出す場合は redaction 後の
safe representation を使う。

## 検証

```powershell
uv run --no-sync werewolf-agent system doctor
```

`system doctor`は設定とpackaged resourceを検証する。databaseやproviderへの外部接続を
伴う確認は個別の preflight として実行する。

## 設定追加

設定を追加する場合は settings model、安全な default、`.env.example`、利用箇所、
検証 test、設計書を同じ変更で更新する。同じ意味の環境変数 alias や暗黙 fallback
は追加しない。
