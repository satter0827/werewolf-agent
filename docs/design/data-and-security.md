(data-security)=
# データとセキュリティ

保存する完全状態、利用者へ返す公開情報、運用上の trace を別のデータ境界として
扱う。公開範囲を保存形式や画面側の判断に依存させない。

## データ分類

| 区分 | 内容 | 公開範囲 |
| --- | --- | --- |
| public state | フェーズ、公開済み結果、閲覧者が選べる操作 | game 参加者 |
| public timeline | 公開イベントの時系列 | game 参加者 |
| player observation | 本人の役職、既知情報、合法な候補 | 認証した player 本人 |
| private state | 役職、夜行動、内部の完全イベント | backend と管理者専用 reveal |
| LLM trace | 観測、構造化出力、provider 情報 | 運用権限を持つ主体 |
| credential | token、API key、秘密鍵 | 実行環境だけ |

## 永続化

Supabase adapter は repository port を実装し、Auth、game state、operation queue、
trace の接続を担当する。React から Supabase へ直接接続する用途は Auth に限定し、
ゲームテーブルは Data API から参照させない。

完全状態を返す reveal は、管理者認可と専用設定を通過する HTTP route に限定する。
通常の `GameClient`、React の game data client、CLI、Streamlit からは呼び出せない。

並行更新は repository 境界で検出する。worker の operation は取得、実行、完了または
失敗の状態を持ち、中断後に未確定な操作を成功扱いしない。

## 秘密情報

- credential は環境変数または実行環境の secret store から取得する。
- `.env`、token、実データを repository と生成物へ保存しない。
- `secret`、`token`、`api_key`、`authorization`、`password` をログ記録前に mask する。
- 例外、HTTP 応答、browser state に内部設定や stack trace を含めない。
- 外部入力を未検証のまま prompt、file path、shell command に渡さない。

## 認証と認可

認証は利用者を特定し、認可は game ごとの操作可否を判断する。両者を一つの
「ログイン済み」判定へまとめない。ID を含む要求は usecase 境界で主体と対象の関係を
検証し、adapter が返した行をそのまま公開しない。

## 検証

public DTO と timeline に秘匿 field が混入しないこと、redaction が入れ子構造でも
働くこと、別利用者の game を操作できないことを自動テストで保証する。
