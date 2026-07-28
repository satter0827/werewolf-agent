# Adapters

`adapters`はHTTP、Supabase、LLM frameworkなどの外部技術を実装する。

- application、agents、contractsが定義する境界を実装する。
- provider固有型をcoreへ漏らさない。
- 外部入力と外部出力を境界で検証、変換、redactionする。
- retry、timeout、接続先はsettingsから受け取る。
