(system-architecture)=
# システムアーキテクチャ

## システム境界

React、CLI、Streamlit は HTTP API だけを通じてゲームを操作する。API と worker が
`GameApplication` を呼び、domain が状態遷移を決定する。Supabase は認証、永続化、
operation queue を担い、worker だけが有料 LLM provider の秘密値を使用する。
通常の利用者境界は公開状態と認証した player 本人の observation だけを返し、完全
状態は設定で有効化した管理者専用 reveal に隔離する。

```{image} ../_generated/architecture/system-context.svg
:alt: UI、API、worker、domain、Supabase、LLM provider の接続関係
:width: 100%
```

## Layer

| Layer | 責務 |
| --- | --- |
| `domain` | aggregate、state、event、rule policy |
| `usecase` | ID、authorization、transaction、projection |
| `agents` | observation、decision、provider 非依存 port |
| `adapters` | HTTP client、Supabase、agent driver |
| `api` | HTTP、認証・認可、composition root |
| `interfaces` | CLI、Streamlit、worker |
| `contracts` | wire schema、error、Problem Details |
| `configuration` | settings、resource、definition validation |
| `security` | principal、redaction |
| `observability` | entrypoint log、context、event sink |
| `resources` | packaged TOML、prompt、fixture |

```{image} ../_generated/architecture/layer-dependencies.svg
:alt: Python layer 間の実 import 依存
:width: 100%
```

## 依存規則

- domain は他 layer を参照しない。
- usecase は外部 service、delivery、agents を参照しない。
- agents は domain と usecase を参照しない。
- API route は注入された application contract だけを呼ぶ。
- API composition root だけが adapter を構築できる。
- CLI と Streamlit は domain、usecase、Supabase repository を参照しない。

`api/bootstrap.py` から `adapters` への依存だけを path 単位の例外として登録する。
API route へ同じ依存を広げず、例外の path と理由を構造分析 JSON に出力する。

これらは実 source の AST から評価する。詳細は
{download}`architecture.json <../_generated/architecture/architecture.json>`と
{download}`architecture.schema.json <../_generated/architecture/architecture.schema.json>`、
{download}`assessment.md <../_generated/architecture/assessment.md>`で確認できる。

## 公開面

Python 利用者向け application 入口は `Actor` と `GameApplication` である。domain、
agents、contracts、adapters は各 package の `__all__` を公開面とし、内部 module を
契約に含めない。
