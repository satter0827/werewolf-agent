(verification)=
# 検証

## 目的

製品の合否をrepository内のsource、test、fixture、local process、Compose serviceから
判定する。package取得先や有料providerの可用性を製品品質と混同しない。

## 品質profile

| Profile | 責務 |
| --- | --- |
| `auto` | 変更pathを責務境界へ対応付け、必要なprofileまたは部分gateを選ぶ |
| `focus` | architecture、format、lint、型、unit、軽量stateful |
| `check` | Focus、unit同時coverage、offline integration、docs、OpenAPI、Schemathesis、build |
| `release` | Check、Supabase、API、worker、clients、browser、package、container |
| `deep` | 長時間stateful、fault injection、性能観測 |
| `review` | UI、Gameplay、Local LLMの読解用証拠。合否には含めない |

`auto`の変更pathと選定結果の対応は`scripts/quality/impact.toml`を正本とする。具体的な
実行command、`--fresh`、個別gate、環境準備は`scripts/README.md`へ集約する。

## 外部接続境界

品質processからprovider credentialと外部base URLを除去し、fake providerとtelemetry
無効化を強制する。Python test、Playwright、E2E containerは非loopback通信を拒否する。
依存取得は`scripts.environment`へ分離し、品質profileは実行中に依存環境を変更しない。
利用者が運用設定として有料providerを選ぶことは許可するが、そのcredential、応答、
可用性を品質判定やreviewの前提にしない。Local LLM reviewはloopbackだけを許可する。

## 判定

- `passed`: 検査を満たす。
- `failed`: assertion、lint、型、契約に違反する。
- `blocked`: tool、権限、Docker、local serviceなどの実行条件が不足する。
- `error`: runnerまたは検査基盤が異常終了する。
- `skipped`: 依存gateが完了していない。

## 構造と成果物

`.werewolf-agent/logs/application`は常駐processの構造化log、`operations`は有限の環境・Supabase
操作、`quality`は品質run、`reviews`は主観reviewを所有する。operation runは`report.json`、
`summary.md`、`manifest.json`と失敗stageのredacted logを持つ。成功commandの全出力は保存しない。
`diagnostics/current`はこれらを参照する再生成可能なviewであり、raw成果物を複製しない。

architecture testは`scripts/architecture/rules.toml`を正本とし、grimpのimport graphから
間接依存と循環を検査する。Hypothesisはdomain操作列の生成と縮小、Schemathesisは
OpenAPIのpositive/negative入力とDeepのstateful操作列、respxはHTTP異常、psutilは
子processと実行中runの所有権を担当する。
構造testはdomainの第三者package、applicationからwire contractへの依存、API routeから
access/queue adapterへの直接呼出し、公開export allowlist、旧plural faction IDを検出する。
OpenAPI operation、`FeatureSpec`、CLI command、Streamlit workspaceの対応と、admin機能の
通常workspace混入も検出する。command登録とrendererのFeature ID宣言も照合し、配置だけが存在する
未実装を許可しない。rule compositionは選択肢0件、1件、複数件、未知ID、保存済みsnapshot、
再戦への引継ぎ、replay再現を検証する。
replay testはcommand、event、state、projection、rule snapshotの改変と旧形式を、最初の
不一致versionで検出する。必須fieldが欠けた破損記録も例外を公開せずunsupportedとして扱う。
domain testは復元snapshotのplayer数、役職構成、終局結果、pending action参照の不整合を拒否する。

最新試行は`.werewolf-agent/quality/profiles/<profile>/current`、以前の試行は
`.werewolf-agent/quality/history/<profile>/<run-id>`へ保存する。最終成功は
`profiles/<profile>/last-passed.json`が指す。

各runは`report.json`、`summary.md`、`events.jsonl`、`manifest.json`を持つ。manifestには
producer、分類、MIME、size、SHA-256、保持状態を記録する。成功runもlog、JSON/HTMLの
test結果、coverage、画面を含む一式でcurrentを置換する。`last-passed.json`は最終成功を指し、
reportは要求したprofile、実際に選ばれたprofile、Autoの選定理由を記録する。
履歴は参照中の最終成功と直近2件の非成功runを保持する。削除可能なのは再生成可能な動画などに
限る。必須証拠が容量上限を超えた場合は削除せず成果物契約違反にする。完了記録のないrunは
次回起動時にhistoryへ回収する。

Python Playwrightはjourney、state、deviceを個別選択し、操作、contract、accessibility、console、
外部通信を判定する。選択肢とcapture filenameは`scripts/browser/catalog.toml`を正本とする。
screenshotはcapture名で選択し、traceは失敗時または明示指定時だけ保存する。
見た目はpixel差分で合否を出さず、setup、validation、待機、発言、対象選択、送信中、完了、
観戦、Recordsの空・記録あり、Settings、縮退表示を含むdesktop/mobileの個別画像、一覧画像、
HTML/JSONを人が読む。狭幅はStreamlit scenario内で独立して確認する。
client fault testはAPI、Auth、database、operation queue、worker、LLM、翻訳overrideを個別に
故障させ、停止範囲が依存するfeatureに限られることを確認する。packaged CSSとview構造はbuild時に
固定し、外部overrideの故障経路を持たない。画面はkeyboard、
focus保持、label、状態通知、200% zoom、reduced motion、contrastも確認する。
i18n overrideの正常系では言語catalogがrendererへ届くことを検証し、異常系では理由をlogへ記録して
packaged catalogへ戻ることを検証する。
環境準備testはmarkerとimage cacheの不一致、Docker daemon停止、全必須imageありを個別に作り、
release系profileだけが現在のDocker contextを検査することを確認する。
release系profileは開始時にDocker labelから品質専用Supabase projectを列挙し、失敗した過去runの
孤児containerとvolumeを回収する。開発用および他projectのSupabaseは対象にしない。
品質runnerはinstalled distributionの正規化名、version、`RECORD` metadataを実行前後で比較し、
品質判定中のPython環境変更を失敗にする。
coverage、benchmark、面白さ、会話品質にも根拠のない閾値を置かず、観測値と証拠を残す。
coverage reportは総合・line・branchに加え、未検証行が多いファイルから有効行数とともに表示し、
少量ずつテストを追加する優先順位を示す。低被覆だけでは品質違反にしない。
Gameplay reviewは現在のrules、roles、abilitiesからseed固定で一局を完走し、設定、操作列、
公開timeline、終局を保存する。解決前の行動対象などprivate情報はreview証拠へ保存しない。
Local LLM reviewは`WEREWOLF_LOCAL_LLM_BASE_URL`と`WEREWOLF_LOCAL_LLM_MODEL`を使い、
base URLがloopbackである場合だけ実行する。`scripts.agents preflight`はmodel一覧と本番Agent
1回のdecision pipeline、`run`は固定1 presetを最大3呼び出し、各40秒timeoutで検証する。
model一覧確認を含む上限は約3分とする。
Local providerのstandard suiteとpreset指定は許可せず、一局完走は`local-ui`へ分離する。
Local LLM、FakeListChatModelとも
同じchat request、response正規化、schema検証、合法手検証、fallbackを通す。再問い合わせによる
修復は行わない。fallbackを伴う完走は`degraded`とし、品質profileの合格へ含めない。

Agent reviewは`.werewolf-agent/reviews/agents`へreport、metrics、event、public timeline、private trace、
SHA-256 manifestを保存する。private traceにはpromptと本人のobservationを含め、公開成果物と
分離する。standardはpreset完了ごとに`checkpoint.json`と関連成果物を更新し、長時間runが
中断しても完了済みpresetを回収できるようにし、完了または中断時にはcheckpointも最終状態へ
確定する。providerが返したtoken usageだけを記録し、取得できない値は推計しない。
Fake standard reviewはpreset、seed、思考レベルごとに完走し、発言の完全重複、focus欠落、
evidence不正、発言と投票の整合、対象固定、profile別の対象差、勝利陣営、ゲーム日数をJSONへ保存する。
これらは観測値とし、根拠のない面白さや勝率の合否閾値を設けない。
`local-ui`は認証済みの専用利用者とAPI driverで一局を完走し、worker traceが`lmstudio`だけで
あることをmodelを含めDBで照合する。品質用resourceを停止しない専用Compose projectを所有し、
最新sourceのimageをbuildしてから起動する。Streamlitの作成直後、進行中、公開timeline、終了、
異常表示を撮影し、contact sheet、console、networkをpublicへ保存する。passwordや認証通信を含み得る
Playwright traceとnative reportはprivateへ保存し、通常の品質browser suiteからは明示Local specを
除外する。品質子processは通常とworker paid modeの両方をFake adapterへ固定する。

自動Browser E2Eの合格、保存済み画像の読解、対話的な画面確認は別の証拠として扱う。
対話操作を実行できない場合はその確認だけを`blocked`とし、自動E2Eの結果を変更しない。
