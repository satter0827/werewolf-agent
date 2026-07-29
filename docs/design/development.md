(development)=
# 開発

## 目的

要求、設計境界、実装、検証、文書を一つの変更単位として扱う。再現可能な操作は
リポジトリ内のコマンドへ実装し、VS Code、CI、AIから同じ入口を使用する。

## 責務

1. 対象のdesign文書、実装、テスト、設定を確認する。
2. 原因を所有責務と依存方向まで絞る。
3. 境界変更をdesign文書とarchitecture manifestへ反映する。
4. 再現テストを追加し、所有モジュールへ実装する。
5. OpenAPI contract、設定例、不要な旧構造を同じ変更で整える。
6. 対象gateと品質プロファイルを実行する。

## Branch

`develope`は日常の統合、`main`はリリース可能な状態を所有する。短期branchは`develope`から
作成し、PRで`develope`へ取り込む。リリースは`develope`から`main`へのPRだけで行う。

すべてのPRはmerge commitで取り込む。squash mergeとrebase mergeは使用せず、共有branchを
force-pushしない。正常なリリース後に`main`を`develope`へ逆mergeしない。

## 境界

- domain ruleはdomain、利用者要求の調整はapplicationに置く。
- 外部技術はadapters、HTTP deliveryはapi、queue実行はworkerに置く。
- CLIとStreamlitはclientsに置き、HTTP contractだけを使用する。
- 可変値はsettingsまたは所有機能のresourceへ置く。
- 互換fallback、未使用path、横断的なconstants/messagesモジュールを残さない。

## 環境

環境targetは`python`、`development`、`quality`とする。`check`はtargetのfingerprint、Docker
context、準備時に記録したimage IDを読み取り専用で確認する。`setup`だけが依存取得、image build、
隔離Supabaseの起動を行う。`development`は品質用imageを構築せず、`quality`だけがBuildxと
app・E2E imageを要求する。隔離projectは固有IDとworkdirで所有し、利用者の開発stackを停止しない。
具体的な環境準備と診断コマンドは`scripts/README.md`を正本とする。

VS Codeの「実行とデバッグ」は`開発: Full Stack`、`開発: Backend`、
`クライアント: Streamlit`、`クライアント: CLI Play`、`デバッグ: API`、`デバッグ: Worker`を
公開する。StreamlitとCLIはバックエンドを暗黙に起動しない。Streamlitはバックエンドがなければ
安全な縮退画面を表示する。バックエンド系compoundは開始前に単一セッションを予約し、競合時は
既存セッションを流用しない。

環境準備、品質、レビュー、report、cleanup、診断はVS CodeのTaskとして公開する。品質Taskは環境を
暗黙に準備しない。stackはローカルSupabaseを含むプロセスを所有し、終了時に自分が起動したprojectだけを
停止する。API、worker、Full Stack用StreamlitはsupervisorがmigrationとCLI由来・`.env`由来の
接続確認を完了した状態を待ってから起動する。秘密値はsupervisor stateと診断へ保存しない。

個別gate、品質プロファイル、ブラウザー、エージェントレビューの具体的なコマンドは
`scripts/README.md`を正本とする。
gateはpytest markerと公開コマンドだけを使い、テストソースコードを解析して選択しない。

`tests/unit`は通常の単体テスト、`tests/integration`は複数モジュールを接続したコード全体の
テストを所有する。OSSとの連携はintegrationの対象に含める。Docker daemon、image、ブラウザー
導入状態などの実行環境はテストで判定せず、環境準備と品質gateが事前条件として扱う。

## 検証

formatter、lint、型、対象テストを先に実行し、変更範囲に応じてFocus、Check、
リリース、Deepへ広げる。完成した仕様は`docs/design`、再利用する調査と引継ぎだけを
`docs/notes`へ置き、完了した一時記録と生成証拠は`.werewolf-agent`へ移す。

`develope`向けPRはCheckを必須とする。`main`向けPRはheadを`develope`に限定し、Deepと
対応Python版の互換性検査を必須とする。`main`へのpushでは同じ検査を再実行しない。
