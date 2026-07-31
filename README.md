# Werewolf Agent

Werewolf Agentは、LLMエージェントを人狼ゲームのプレイヤーとして動かす決定的な
Python SDKである。標準インストールは第三者パッケージに依存せず、完全状態とルールを管理する
domain coreを提供する。FastAPI、CLI、Streamlit、workerはextraとして明示した境界で接続する。
公開状態、public timeline、本人のobservationを分離し、既定のFakeListChatModelだけで
外部APIなしに再現できる。

Streamlitが唯一のブラウザーUIである。CLIとStreamlitは同じHTTP APIを使い、Supabaseが
Auth、PostgreSQL永続化、PGMQ操作キューを担当する。

## プロジェクトの状態

本リポジトリはAlpha段階である。公開APIと設定はversion契約に従って管理するが、安定版までの
後方互換は保証しない。

## 主な機能

- seedと設定を固定してゲームを再現する。
- manifest付き外部Rule Packを明示登録し、能力・投票・勝敗Policyを一局へ固定する。
- 公開状態、public timeline、本人のobservationを分離する。
- CLI、Streamlit、workerを同じHTTP APIへ接続する。
- Fake LLMとlocalhostだけで通常の品質検証を完結する。

## Python API

リポジトリからwheelを構築してinstallすると、外部serviceを起動せずに決定的なdomain coreを
利用できる。

```powershell
python -m pip install .
```

標準インストールにruntimeの第三者依存はない。提供層を使う場合は利用単位のextraを指定する。

```powershell
python -m pip install ".[application]"
python -m pip install ".[cli]"
python -m pip install ".[api]"
python -m pip install ".[llm]"
python -m pip install ".[streamlit]"
python -m pip install ".[worker]"
```

`application`はuse case contract、`llm`はLangChainアダプターだけを組み込む場合に指定する。
複数の提供層を同じ環境で使う場合は、`".[api,cli,streamlit,worker]"`のようにまとめて指定する。

主要なdomain型は`werewolf_agent.domain`からimportする。次の例は外部serviceや設定fileを使わずに
3人ゲームを作成し、公開発言を1件登録する。ゲーム作成時はプレイヤー、規則、seed付き乱数を
明示して渡し、状態変更は`Game`を通じて行う。

```python
import random

from werewolf_agent.domain import (
    Action,
    Game,
    GameSetup,
    LocalRules,
    Player,
    RoleCatalog,
    RoleDefinition,
    RuleSetDefinition,
    build_game_rules,
)

rules = build_game_rules(
    RuleSetDefinition(
        player_count=3,
        role_counts={"villager": 2, "werewolf": 1},
        rules=LocalRules(
            day_speech_limit_per_player=1,
            allow_self_vote=False,
            allow_vote_revision=False,
            allow_night_action_revision=False,
            vote_tie_resolution="no_elimination",
            starting_phase="day_discussion",
            reveal_role_on_death=True,
        ),
        roles=RoleCatalog(
            {
                "villager": RoleDefinition("village", "village"),
                "werewolf": RoleDefinition("werewolf", "werewolf"),
            }
        ),
        abilities={},
    )
)
game = Game.create(
    GameSetup(
        players=(
            Player("p1", "Alice"),
            Player("p2", "Bob"),
            Player("p3", "Carol"),
        )
    ),
    rules=rules,
    random=random.Random(7),
)
game.submit(Action.speech("p1", "状況を確認します。"))
observation = game.view_for("p1")
```

`werewolf_agent.setup`は第三者packageに依存せず、完全setupの検証、Domain Rule Definition変換、
用途別seed、正規checksum、immutableなプレイヤー generation定義を提供する。
`GameSetupDocument.from_mapping()`で完全setupを構築し、同じ定義とseedを`generate_players()`へ
渡すと、同じ公開personaとprivate strategyを持つrosterを再生成できる。

設定済みの6人ゲームとFakeListChatModelを使った一連の操作は
[quickstart Notebook](notebooks/quickstart.ipynb)で確認できる。Notebook専用コードは製品の
wheelとsdistに含めない。

```powershell
uv run --with jupyterlab jupyter lab notebooks/quickstart.ipynb
```

## 前提環境

- [pyproject.toml](pyproject.toml)の`requires-python`を満たすPython
- [uv](https://docs.astral.sh/uv/)
- Docker Desktop
- Supabase CLI

依存とローカルtoolを準備し、設定とpackaged resourceを検査する。

```powershell
uv run --no-project python -m scripts.environment setup python
uv run --no-project python -m scripts.environment check python
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

個別プロセスはconsole entrypointまたは`.vscode/launch.json`から起動できる。VS Codeでは
Full Stack、バックエンド、Streamlit、CLI Play、API debug、Worker debugを独立して選択する。

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

## 参加と報告

変更を提案する場合は[Contributing](CONTRIBUTING.md)を参照する。脆弱性は公開Issueへ記載せず、
[Security Policy](SECURITY.md)に従って報告する。一般的な不具合と機能提案は
[GitHub Issues](https://github.com/satter0827/werewolf-agent/issues)で受け付ける。

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

[MIT License](LICENSE)
