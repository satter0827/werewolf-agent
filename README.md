# Werewolf Agent

Werewolf Agentは、LLM agentを人狼ゲームのplayerとして動かすPython applicationです。
決定的なdomain coreが完全状態とルールを管理し、FastAPI、CLI、Streamlit、workerを
明示した境界で接続します。公開状態、public timeline、本人のobservationを分離し、
既定のFakeListChatModelだけで外部APIなしに再現できます。

Streamlitが唯一のbrowser UIです。CLIとStreamlitは同じHTTP APIを使い、Supabaseが
Auth、PostgreSQL永続化、PGMQ operation queueを担当します。

## 前提環境

- Python 3.11以上3.15未満
- [uv](https://docs.astral.sh/uv/)
- Docker Desktop
- Supabase CLI

依存とローカルtoolを準備し、設定とpackaged resourceを検査します。

```powershell
uv run --no-project python -m scripts.environment setup check
uv run --no-sync werewolf-agent system doctor
```

Supabaseを使う場合は`.env.example`を`.env`へコピーし、公開keyとworker用DB DSNを
設定してからpreflightを実行します。秘密値はversion管理しません。

```powershell
uv run --no-sync python -m scripts.supabase preflight
```

## 最短実行

標準6人templateと固定seedでゲームを実行します。

```powershell
uv run --no-sync werewolf-agent game play --template standard_6 --seed 1
```

完全なsetup documentを編集する場合は、同梱templateをTOMLへ出力して検証します。

```powershell
uv run --no-sync werewolf-agent setup export --template standard_6 --output-file game-setup.toml
uv run --no-sync werewolf-agent setup validate game-setup.toml
uv run --no-sync werewolf-agent game create --setup-file game-setup.toml --seed 1
```

API、worker、Streamlit、local Supabaseをまとめて起動する場合はDocker Composeを使います。

```powershell
docker compose --profile dev up --build
```

個別processはconsole entrypointまたは`.vscode/launch.json`から起動できます。

```powershell
uv run --no-sync werewolf-agent-api
uv run --no-sync werewolf-agent-worker run
uv run --no-sync streamlit run src/werewolf_agent/clients/streamlit/app.py
```

## 文書

設計、公開API、開発、検証、release、運用の正本は[Sphinx文書](docs/index.md)です。
品質profile、環境準備、Browser E2E、Agent reviewの具体的な操作は
[scripts運用ガイド](scripts/README.md)を参照します。

```powershell
uv run --no-sync python -m scripts.docs inspect
uv run --no-sync python -m scripts.docs build
```

生成HTMLは`.werewolf-agent/outputs/docs/index.html`、構造分析は
`.werewolf-agent/outputs/architecture`へ保存されます。生成物はGitへ追加しません。

## 検証

通常の変更では、差分から必要なprofileまたはgateを選択します。

```powershell
uv run --no-sync python -m scripts.quality auto
```

品質判定はfixture、Fake LLM、localhost、Compose内serviceで完結し、有料providerや
任意の外部APIを使用しません。結果は
`.werewolf-agent/quality/profiles/<profile>/current`へ保存され、最終成功は同じprofileの
`last-passed.json`が指します。

## 主要境界

- `Game`だけがゲーム状態を変更する。
- domainは標準libraryとdomain内部だけに依存する。
- applicationとagentsは互いに依存しない。
- API routeはapplicationの公開contractだけを呼ぶ。
- CLIとStreamlitはHTTP APIだけでゲームを操作する。
- public state、timeline、LLM observationへ秘匿情報を含めない。
- 外部LLM出力はschemaと合法手を検証してからactionへ変換する。

詳しい責務と依存方向は[システムアーキテクチャ](docs/design/architecture.md)を参照してください。

## License

MIT License
