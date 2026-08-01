(data-security)=
# データとセキュリティ

保存する完全状態、利用者へ返す公開情報、運用上のtraceを別のデータ境界として
扱う。公開範囲を保存形式や画面側の判断に依存させない。

## データ分類

| 区分 | 内容 | 公開範囲 |
| --- | --- | --- |
| public state | フェーズ、公開済み結果、閲覧者が選べる操作 | game参加者 |
| public timeline | 公開イベントの時系列 | game参加者 |
| プレイヤーobservation | 本人の役職、既知情報、合法な候補 | 認証したプレイヤー本人 |
| private state | 役職、夜行動、内部の完全イベント | バックエンドと管理者専用reveal |
| LLM trace | 観測、構造化出力、provider情報 | 運用権限を持つ主体 |
| credential | token、API key、秘密鍵 | 実行環境だけ |

```{image} ../_generated/architecture/information-boundaries.svg
:alt: 完全状態からpublic state、本人observation、管理者revealを分離する流れ
:width: 100%
```

完全状態から外部出力を作る各経路は独立したallowlist projectionを持つ。public projectionは閲覧者に
依存せず、プレイヤーprojectionは認可主体とプレイヤーIDを検証し、revealは管理者認可と機能設定の両方を
必要とする。完全状態を通常clientへ送って画面側で隠さない。

死亡時役職公開が有効な場合だけ、死亡者のroleとfactionをpublic stateへ移す。通常のpublic
stateは終局後も全役職を公開せず、完全状態は管理者revealと認可済みreplayに限定する。

## 永続化

Supabaseアダプターはリポジトリportを実装し、公式Auth SDK、game state、PGMQ、
traceの接続を担当する。APIとworkerは用途別のプロセス所有connection poolを使う。
Supabase Authとゲームテーブルを分離し、ゲームテーブルはData APIから参照させない。

完全状態を返すrevealは、管理者認可と専用設定を通過するHTTP routeに限定する。
通常の`GameClient`からは呼び出せない。CLIとStreamlitの
管理者領域は、管理者認可を通過した`AdminClient`だけから呼び出す。完全情報を通常clientで
取得してから画面で隠す実装は禁止する。

並行更新はリポジトリ境界で検出する。workerのoperationは取得、実行、完了または
失敗の状態を持ち、中断後に未確定な操作を成功扱いしない。

acceptedコマンドはactor、期待version、正規化済み入力、再現に必要なseedと自動プレイヤーの
domain actionを保存する。作成時のrule snapshotから集約を再構築し、version順にコマンドを
再適用してstate、event、public projectionを照合する。checksumは破損検出に使用し、再実行の
代用にしない。各game versionのコマンド、event、state、projectionは同じtransactionで
追記し、同じversionを上書きしない。旧形式は暗黙変換せずunsupportedとして扱う。

## 秘密情報

- credentialは環境変数または実行環境のsecret storeから取得する。
- CLIのSupabase sessionはOS credential storeだけへ保存し、平文fileへfallbackしない。
- `.env`、token、実データをリポジトリと生成物へ保存しない。
- `secret`、`token`、`api_key`、`authorization`、`password`をログ記録前にmaskする。
- 例外、HTTP応答、ブラウザーstateに内部設定やstack traceを含めない。
- 外部入力を未検証のままprompt、file path、shellコマンドに渡さない。

## 認証と認可

認証は利用者を特定し、認可はgameごとの操作可否を判断する。両者を一つの
「ログイン済み」判定へまとめない。IDを含む要求はapplication境界で主体と対象の関係を
検証し、アダプターが返した行をそのまま公開しない。

## 検証

public DTOとtimelineに秘匿fieldが混入しないこと、redactionが入れ子構造でも
働くこと、別利用者のgameを操作できないことを自動テストで保証する。
公開eventはallowlistへ射影してから保存し、死亡時役職公開が無効ならroleとfactionを除く。
