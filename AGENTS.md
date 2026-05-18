# AGENTS.md

このファイルは、このリポジトリで作業する AI コーディングエージェント向けの作業ガイドです。
リポジトリ配下のすべてのファイルに適用されます。より深い階層に別の `AGENTS.md` がある場合は、そちらの指示を優先してください。

## Project Overview

Werewolf Agent は、LLM エージェントをプレイヤーとして参加させる人狼ゲームです。

このプロジェクトの主なゴール:

- LLM 同士の人狼シミュレーションを実現する
- 最終的に Web で遊べる、または観戦できる形にする
- デプロイ可能なポートフォリオ作品として完成させる

最初の到達点は、CLI で 1 ゲームを完走できることです。

重要な設計原則:

- ゲーム状態、役職処理、投票集計、勝敗判定は決定的なゲームエンジンで管理する
- LLM は発話、推理、投票、能力使用の意思決定を担当する
- LLM に渡す情報は、各プレイヤーが観測可能な情報に限定する
- LLM の出力は自由文のまま使わず、構造化データとして検証する
- 会話ログ、観測情報、行動、投票、勝敗を後から分析できる形で保存する
- API 化を前提にし、将来のフロントエンドを自由に差し替えられるようにする
- 会話体験はチャット形式を基本方針にする

## Repository Layout

現在の想定構成:

```text
.
├── backend/       # Python backend, game engine, agents, LLM adapters
├── front-web/     # Web UI
├── docs/          # Design notes and project documentation
├── tests/         # Automated tests
├── README.md
├── AGENTS.md
└── LICENSE
```

実装が増えた場合は、既存の構成と命名に合わせてください。大きな構成変更が必要な場合は、先に README または docs に設計意図を残してください。

## Working Principles

- 小さく、検証しやすい変更を優先する
- 可能な限りデファクトな構成、形式、設計にする
- 既存の設計、命名、依存関係に合わせる
- 関係のないリファクタリングや整形だけの変更を混ぜない
- ユーザーや他のエージェントが加えた変更を勝手に戻さない
- 実装前に近いコード、README、docs、テストを確認する
- 不確かな仕様は、推測で固定せず docs に前提を書く
- セキュリティ、API キー、ログ出力、LLM の観測範囲に関わる変更は慎重に扱う

## Review Criteria

変更をレビューするときは、単なる構文確認ではなく、次の観点を優先してください。

- ステージ済み変更を起点に、関連する README、docs、テスト、近い実装と照合する
- 設定値駆動になっているか確認する。環境差分、LLM provider / model、Django 設定、ゲーム設定、ログ設定、秘密情報をコードに直書きしない
- 同じ処理や定数が散らばっていないか確認し、共通設定、共通関数、既存ライブラリ、標準的な API でコード量を減らせる場合は寄せる
- デファクトな形式、命名、ツール、ディレクトリ構成に沿っているか確認する。フォルダ名やモジュール名が責務を直感的に表していない場合は、実装を広げる前に命名を見直す。独自形式を増やす場合は理由を docs に残す
- 新しい設定値を追加した場合は、安全なデフォルト、`.env.example`、README / docs、テストが同じ意味で揃っているか確認する
- CLI / API / UI など外部境界では、内部例外、stack trace、secret をそのまま出さず、安定したエラーコードや公開スキーマに変換されているか確認する
- 共有すべき開発設定と個人環境依存の設定を分ける。IDE 設定や生成物を入れる場合は、パスや秘密情報がローカル固定になっていないか確認する
- LLM に渡す観測範囲、ログ出力、API キー、認証情報に漏えいリスクがないか確認する
- 変更範囲に見合うテスト、lint、format check、type check を実行し、実行できない場合は理由と残リスクを残す
- コミットメッセージ案は日本語を基本にし、`feat: ...`、`fix: ...`、`docs: ...` など Conventional Commits に近いデファクトな形式にする

## Backend Guidelines

バックエンドは Python + uv + Django + LangChain で実装する想定です。

- Package manager は `uv` を優先する
- Python は 3.11+ を想定する
- Web/API 層は Django を基本にする
- API を公開する場合は、Django REST Framework など Django で一般的な構成を優先する
- LangChain は LLM provider の切り替え、prompt 管理、chain 構築などに使い、ゲームルールの中核には混ぜない
- ルール処理は純粋な関数または副作用の少ないサービスとして実装する
- ドメイン層は LLM provider、UI、ファイル I/O に依存させない
- LLM 呼び出しは adapter 層に閉じ込める
- 構造化データの検証には Pydantic などの型付きモデルを使う
- ランダム性を使う処理には seed を注入できるようにする
- 失敗時に再試行可能な境界と、即時に失敗すべき境界を分ける

推奨レイヤー:

```text
domain       # roles, phases, rules, state, win conditions
application  # use cases and game orchestration
agents       # LLM, dummy, human, scripted agents
llm          # provider clients, prompts, structured output parsing
observation  # logging, replay, evaluation
interfaces   # CLI, API, notebooks
```

## Frontend Guidelines

UI は段階的に拡張します。

1. まず CLI で 1 ゲームを完走できるようにする
2. 次に Streamlit で簡易 UI / 観戦 UI を作る
3. いずれ React で本格的な Web UI に拡張する

React の Web UI を実装する場合は、`front-web/` 配下に置いてください。Streamlit は Python 側の interface として扱い、配置場所は既存構成に合わせてください。

- まず実際に遊べる、または観戦できる画面を作る
- ゲーム状態、チャットログ、投票、夜行動、勝敗が読み取りやすい UI を優先する
- UI はバックエンドの内部モデルに密結合させず、明示的な API / DTO を通す
- 状態遷移が見えるよう、フェーズ、日数、生存者、死亡者、投票状況を表示する
- API キーや LLM provider の秘密情報をブラウザに露出しない

## Commands

実装が追加されたら、README とこのファイルのコマンドを更新してください。

標準候補:

```bash
uv sync --group dev
uv run werewolf-agent doctor
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy backend/src
```

Web UI が追加された場合は、`front-web/README.md` または `package.json` の scripts を正としてください。

## Testing

- ゲームルール、勝敗判定、投票集計、役職能力はユニットテストを優先する
- LLM provider を直接呼び出すテストは、通常の単体テストから分離する
- LLM の出力はモックまたは fixture で再現可能にする
- ランダムなゲーム進行は seed を固定してテストする
- バグ修正時は、可能な限り再現テストを追加する
- 外部 API を使うテストは integration test として明示する

## LLM Agent Contract

LLM エージェントを実装する場合は、以下を守ってください。

- ローカル LLM は LM Studio を主な想定の 1 つとする
- OpenAI、Anthropic、Google など主要 LLM API も設定で差し替えられるようにする
- provider、model、base URL、API key、temperature などは設定から変更できるようにする
- エージェントには、そのプレイヤーが知ってよい情報だけを渡す
- 役職、他プレイヤーの正体、夜行動などの秘匿情報を漏らさない
- プロンプトはコードに直書きしすぎず、再利用と差分確認がしやすい形にする
- 出力は JSON Schema、Pydantic model、または同等の仕組みで検証する
- 不正な出力、タイムアウト、空応答に対する fallback を用意する
- ログには API キー、認証情報、不要な個人情報を含めない

## Game Design

人狼の会話体験はチャット形式を基本にします。

- 昼のチャット、投票、夜行動を明確なフェーズとして扱う
- プレイヤーごとのチャット発言、投票理由、能力結果をログに残す
- 秘匿情報は本人または該当陣営にのみ見えるようにする
- 最初に遊べる範囲では複雑な役職や例外ルールを増やしすぎず、標準的な進行を優先する
- ルール差分や独自解釈を入れる場合は、`docs/` に仕様として残す

## Logging and Observability

ゲームログは、後からリプレイ、分析、デバッグできる構造にしてください。

記録すべき情報:

- game id
- seed
- game config
- player ids and public names
- assigned roles, when debug or private log is enabled
- phase transitions
- observations sent to each agent
- structured agent actions
- votes and resolved outcomes
- win result
- errors and fallback decisions

公開用ログとデバッグ用ログは分けてください。秘匿情報を含むログを UI や公開ファイルに出さないでください。

## Documentation

- README は利用者向けの入口として保つ
- 詳細設計、判断理由、仕様メモは `docs/` に置く
- 新しいコマンド、環境変数、設定ファイルを追加したら README または該当 docs を更新する
- ドキュメントは日本語を基本とし、コード識別子や外部 API 名は英語のまま扱う
- 設計書は日本語で書く
- ドキュメントは常にバイブコーディングに都合の良い形にする
- 途中参加した人間や AI がすぐ再開できるよう、「目的」「現在の状態」「実行コマンド」「完了条件」「未決事項」を優先して書く
- 長い背景説明より、次の一手が分かる構造を優先する
- 不確かな仕様は断定せず、前提・未決・選択肢として残す

## Style

- コード識別子、ファイル名、API フィールド名は英語を使う
- Python の docstring は Google style を使う
- コメントは、意図や制約がコードから読み取りにくい場合にだけ書く
- 例外メッセージとログは、原因と次の調査手順が分かる内容にする
- 型ヒントを積極的に使う
- フォーマットはプロジェクトに設定された formatter に従う

## Security

- `.env`、API キー、トークン、秘密鍵をコミットしない
- `.env.example` にはダミー値だけを書く
- LLM への入力に秘密情報を含めない
- ログ出力前に secret、token、authorization header を除去する
- 外部入力をそのままプロンプト、ファイルパス、シェルコマンドに渡さない

## Pull Request Checklist

変更を完了する前に確認してください。

- [ ] README または docs の更新が必要か確認した
- [ ] 関連するテストを追加または更新した
- [ ] 利用可能なテスト、lint、format check を実行した
- [ ] LLM 呼び出しがモック可能であることを確認した
- [ ] ログに機密情報が含まれないことを確認した
- [ ] ゲームルールの変更が既存仕様と矛盾しないことを確認した

## When Blocked

必要な依存関係、API キー、外部サービス、未確定仕様がないと進められない場合は、次の形で状況を残してください。

- 何が不足しているか
- どの作業が完了しているか
- どのコマンドを実行したか
- 次に人間が判断すべき選択肢

可能であれば、外部 API なしで動く dummy agent または mock provider を先に実装してください。
