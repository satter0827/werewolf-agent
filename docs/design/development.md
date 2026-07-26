(development)=
# 開発

## 目的

要求、設計境界、実装、検証、文書を一つの変更単位として扱う。再現可能な操作は
repository内のcommandへ実装し、VS Code、CI、AIから同じ入口を使用する。

## 責務

1. 対象のdesign文書、実装、テスト、設定を確認する。
2. 原因を所有責務と依存方向まで絞る。
3. 境界変更をdesign文書とarchitecture manifestへ反映する。
4. 再現テストを追加し、所有moduleへ実装する。
5. generated contract、設定例、不要な旧構造を同じ変更で整える。
6. 対象gateと品質profileを実行する。

## 境界

- domain ruleはdomain、利用者要求の調整はapplicationに置く。
- 外部技術はadapters、HTTP deliveryはapi、queue実行はworkerに置く。
- CLIとStreamlitはclientsに置き、HTTP contractだけを使用する。
- 可変値はsettingsまたは所有機能のresourceへ置く。
- 互換fallback、未使用path、横断的なconstants/messages moduleを残さない。

## 環境

```powershell
uv run --no-project python -m scripts.environment setup check
uv run --no-sync werewolf-agent doctor
```

`ensure`はlockとtool versionのfingerprintを確認し、不足または変更時だけ同期する。
registry、browser配布元、image registryへの接続は環境準備で許可する。

VS Codeの「実行とデバッグ」では`Run: React Stack`、`Run: Streamlit Stack`、
`Run: CLI Play`、`Debug: API`、`Debug: Worker`を使う。`Verify: Quality`は
Quick/Check/Release/Deep、`Review: Evidence`はUI/Gameplay/Local LLMを選択する。
`Open: Latest Quality Report`と`Cleanup: Owned Resources`も同じ場所から実行する。
選択は`pickString`で行い、commandや引数を手入力しない。Ensure、Supabase、Frontend
起動taskは内部実装として候補から隠す。stackはローカルSupabaseを含むprocessを所有し、
debug sessionの終了時にまとめて停止する。

個別gateはAI、CI、重点調査向けに`python -m scripts.quality gate <selector>`を残す。
gateはpytest markerと公開commandだけを使い、test sourceを解析して選択しない。

## 検証

formatter、lint、型、対象テストを先に実行し、変更範囲に応じてQuick、Check、
Release、Deepへ広げる。完成した仕様は`docs/design`、調査と引継ぎは`docs/notes`に置く。
