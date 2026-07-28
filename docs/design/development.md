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

## 境界

- domain ruleはdomain、利用者要求の調整はapplicationに置く。
- 外部技術はadapters、HTTP deliveryはapi、queue実行はworkerに置く。
- CLIとStreamlitはclientsに置き、HTTP contractだけを使用する。
- 可変値はsettingsまたは所有機能のresourceへ置く。
- 互換fallback、未使用path、横断的なconstants/messagesモジュールを残さない。

## 環境

`check`はlockとソースコードのfingerprint、現在のDocker context、準備時に記録したimage IDを
読み取り専用で確認する。`setup`だけが依存取得、image build、隔離Supabaseの起動を行う。
リリース系setupはDocker daemon、Buildx、Supabase CLIの固定versionを先に検査し、失敗時は
変更を開始しない。隔離projectは固有IDとworkdirで所有し、利用者の開発stackを停止しない。
具体的な環境準備と診断コマンドは`scripts/README.md`を正本とする。

VS Codeの「実行とデバッグ」では`Run: Streamlit Stack`、
`Run: CLI Play`、`Debug: API`、`Debug: Worker`を使う。`Verify: Quality`は
Auto/Focus/Check/リリース/Deep、`Review: Evidence`はUI/Gameplay/Local LLMを選択する。
`Open: Latest Quality Report`と`Cleanup: Owned Resources`も同じ場所から実行する。
選択は`pickString`で行い、コマンドや引数を手入力しない。Environment CheckとSetupを分離し、
Verifyは暗黙に環境を変更しない。stackはローカルSupabaseを含むプロセスを所有し、debug sessionの
終了時に自分が起動したprojectだけを停止する。API、worker、Streamlitはsupervisorがmigrationと
接続確認を完了した状態を読み取り専用で待ってから起動する。

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
