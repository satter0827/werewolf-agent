(evidence-diagnostics)=
# 品質証拠と診断

## 対象と責務

品質実行、有限のリポジトリ操作、常駐プロセス、主観レビューの成果物を、目的ごとに分離する。
機械判定は構造化report、人の初動調査は要約と参照先を使用し、同じraw成果物を複製しない。

| 区分 | 保存先 | 内容 |
| --- | --- | --- |
| application | `.werewolf-agent/logs/application` | 常駐プロセスの構造化ログ |
| operation | `.werewolf-agent/operations` | 環境準備、Supabaseなど有限操作のrun |
| quality | `.werewolf-agent/quality` | gateと品質プロファイルの判定証拠 |
| レビュー | `.werewolf-agent/reviews` | ブラウザー、Gameplay、Local LLMの読解用証拠 |
| diagnostics | `.werewolf-agent/diagnostics/current` | 既存成果物をpathとhashで参照する再生成可能なview |

## 品質run

各runは`report.json`、`summary.md`、`events.jsonl`、`manifest.json`を持つ。manifestはproducer、
分類、MIME、size、SHA-256、保持状態を記録し、未完了gateも`skipped`として確定する。

最新試行は`.werewolf-agent/quality/profiles/<profile>/current`、以前の試行は
`.werewolf-agent/quality/history/<profile>/<run-id>`へ保存する。最終成功は
`profiles/<profile>/last-passed.json`が指す。保持数と容量は設定を正本とし、文書へ固定しない。

operation runは`report.json`、`summary.md`、`manifest.json`と、失敗stageのredactedログを持つ。
成功コマンドの全出力は保存しない。完了記録のないrunは次回起動時に回収する。

## ブラウザー証拠

Python Playwrightはjourney、state、deviceを個別選択し、操作、contract、accessibility、console、
外部通信を検査する。選択肢とcapture filenameは`scripts/browser/catalog.toml`を正本とする。
screenshotはcapture名で選択し、traceは失敗時または明示指定時だけ保存する。

見た目はpixel差分だけで判定しない。desktopとmobileで主要状態を独立して撮影し、一覧画像、
HTML、JSONとともに人が読む。keyboard、focus保持、label、状態通知、200% zoom、reduced motion、
contrastも別の検査として確認する。

自動ブラウザーE2E、保存画像の読解、対話的な画面確認は別の証拠として扱う。対話操作を実行できない
場合はその確認だけを`blocked`とし、自動E2Eの結果を変更しない。

## エージェントレビュー

Gameplayレビューは現在のrules、roles、abilitiesからseed固定で一局を完走し、設定、操作列、
公開timeline、終局を保存する。解決前の行動対象などprivate情報は公開証拠へ保存しない。

Fakeと実LLMは同じchat request、response正規化、schema検証、合法手検証、fallbackを通る。
Local LLMレビューはloopbackだけを許可し、一局完走は`local-ui`へ分離する。fallbackを伴う完走は
`degraded`とし、品質プロファイルの合格へ含めない。

エージェントレビューはreport、metrics、event、public timeline、private trace、SHA-256 manifestを
分離して保存する。providerが返したtoken usageだけを記録し、取得できない値は推計しない。
発言の重複、根拠、投票整合、対象分布、勝利陣営、ゲーム日数は観測値として扱う。

## 診断

`scripts.diagnostics collect`はapplicationログ、operation、quality、レビューを複製せず、pathと
SHA-256で参照する。`report.json`を機械判定、`summary.md`を人の初動調査に使用する。

診断は観測事実、確定原因、仮説、未確認範囲を分離する。subprocessの失敗だけから根本原因を
推測せず、error code、run ID、trace ID、operation IDから直接検査した事実を記録する。
