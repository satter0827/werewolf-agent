# Werewolf Agent

Werewolf Agentは、LLMエージェントを人狼ゲームのプレイヤーとして動かすPython
バックエンドである。決定的なドメインコアが完全状態とルールを管理し、FastAPI、CLI、
Streamlit、workerを明示した境界で接続する。公開状態、public timeline、本人のobservationを分離し、
既定のFakeListChatModelだけで外部APIなしに再現できる。

Streamlitが唯一のブラウザーUIである。CLIとStreamlitは同じHTTP APIを使い、Supabaseが
Auth、PostgreSQL永続化、PGMQ操作キューを担当する。

## 前提環境

- [pyproject.toml](pyproject.toml)の`requires-python`を満たすPython
- [uv](https://docs.astral.sh/uv/)
- Docker Desktop
- Supabase CLI

依存とローカルtoolを準備し、設定とpackaged resourceを検査する。

```powershell
uv run --no-project python -m scripts.environment setup check
uv run --no-project python -m scripts.environment check check
uv run --no-sync werewolf-agent system doctor
```

Supabaseを使う場合は`.env.example`を`.env`へコピーし、公開keyとworker用DB DSNを
設定してから所有権付きsupervisorを起動する。秘密値はversion管理しない。

```powershell
uv run --no-sync python -m scripts.supabase serve --stop-on-exit
```

## 最短実行

標準6人templateと固定seedでゲームを実行する。

```powershell
uv run --no-sync werewolf-agent game play --template standard_6 --seed 1
```

完全なsetup documentを編集する場合は、同梱templateをTOMLへ出力して検証する。

```powershell
uv run --no-sync werewolf-agent setup export --template standard_6 --output-file game-setup.toml
uv run --no-sync werewolf-agent setup validate game-setup.toml
uv run --no-sync werewolf-agent game create --setup-file game-setup.toml --seed 1
```

API、worker、Streamlit、local Supabaseをまとめて起動する場合はDocker Composeを使う。

```powershell
docker compose --profile dev up --build
```

個別プロセスはconsole entrypointまたは`.vscode/launch.json`から起動できる。

```powershell
uv run --no-sync werewolf-agent-api
uv run --no-sync werewolf-agent-worker run
uv run --no-sync streamlit run src/werewolf_agent/clients/streamlit/app.py
```

## 文書

設計、公開API、開発、検証、リリース、運用の正本は[Sphinx文書](docs/index.md)である。
品質プロファイル、環境準備、ブラウザーE2E、エージェントレビューの具体的な操作は
[scripts運用ガイド](scripts/README.md)を参照する。

```powershell
uv run --no-sync python -m scripts.docs inspect
uv run --no-sync python -m scripts.docs build
```

生成HTMLは`.werewolf-agent/outputs/docs/index.html`へ保存される。生成物はGitへ追加しない。

## 検証

通常の変更では、差分から必要なプロファイルまたはgateを選択する。

```powershell
uv run --no-sync python -m scripts.quality auto
```

品質判定はfixture、Fake LLM、localhost、Compose内serviceで完結する。プロファイル、
成果物、診断、ブラウザーE2E、エージェントレビューの操作は[scripts運用ガイド](scripts/README.md)を参照する。

## 主要境界

- `Game`だけがゲーム状態を変更する。
- domainは標準libraryとdomain内部だけに依存する。
- applicationとagentsは互いに依存しない。
- API routeはapplicationの公開contractだけを呼ぶ。
- CLIとStreamlitはHTTP APIだけでゲームを操作する。
- public state、timeline、LLM observationへ秘匿情報を含めない。
- 外部LLM出力はschemaと合法手を検証してからactionへ変換する。

詳しい責務と依存方向は[システムアーキテクチャ](docs/design/architecture.md)を参照する。

## License

MIT License
