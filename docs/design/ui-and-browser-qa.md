# React、Streamlit、Browser QA

## 画面の位置付け

Reactを本番UI、Streamlitを同じ機能契約を確認するMOCとします。両者はゲーム状態を計算せず、FastAPIが返す公開状態、observation、合法行動、設定値だけを表示します。

```text
React     -> generated OpenAPI client -> FastAPI
Streamlit -> HttpGameClient           -> FastAPI
CLI       -> HttpGameClient           -> FastAPI
```

ReactからSupabaseへ接続する用途はAuthだけです。Data API、RPC、Realtimeによるゲーム操作は禁止し、ESLintと構造テストで検査します。

## React

desktopはゲーム卓、action panel、timelineを同時に表示します。mobileはaction panelを下部へ固定し、主要状態を先に読み取れる順序へ変えます。themeはCSS custom propertyへ集約します。

- keyboardと`focus-visible`
- label、landmark、ARIA
- 色以外の状態表示
- reduced motionとforced colors
- provider名、model名、内部operation IDの非表示
- 観戦画面はpublic stateとpublic timelineだけを利用し、管理APIを呼ばない
- private observationの取得はプレイ画面だけに限定する
- ゲスト利用とemail/passwordログイン、ログアウト
- プレイヤー参加と観戦専用のgame作成
- 進行中gameの再開と完了済みgameの結果表示

## Streamlit

標準componentと最小限のCSSを使い、入力制約と合法行動はAPI応答をそのまま使用します。React固有の演出は再現しません。「MOC」という開発上の名称は利用者向け本文へ表示しません。
sidebarは標準の`auto`状態とし、desktopではナビゲーションを表示し、狭い画面では本文の
操作を覆わないよう折りたたみます。

## Browser QA

必要なNode依存は`@playwright/test`、`@axe-core/playwright`、`msw`です。

```bash
cd frontend
npm ci
npm run test:e2e
```

E2EではAPIのruntime設定と次のDOM属性を照合します。

- `data-contract-version`
- `data-config-revision`
- `data-game-version`
- `data-message-max-chars`
- `data-operation-status`
- `data-view-mode`
- `data-theme-id`
- `data-compact-layout`

responsive切替は`ui.desktop_breakpoint`をReactが評価し、`data-compact-layout`へ反映します。
固定media queryへ同じ値を重複定義しません。E2Eではdesktopとmobileの導線、computed
CSS、keyboard focus、色コントラストを含むaxe、operation待機、エラー復帰を確認します。
文章上限はAPIの`limits.message_max_chars`を唯一の公開ソースとし、
`data-message-max-chars`、Reactの`maxlength`、Streamlitの`max_chars`、
APIの受理条件を照合します。action formが現れる局面はdomain状態に依存するため、
browser testは常時存在するDOM属性、component testは実際の`maxlength`を検証します。
認証とDBを伴うE2Eは
local Supabaseを起動して実行します。

Streamlitのaxe検証では、Streamlit自身がsidebarの`section`へ付与する非対応の
`aria-expanded`と、number inputの増減ボタンだけをframework所有要素として判別します。
sidebar全体は除外せず、配下のログイン、履歴、入力、操作も検査します。この例外は
Reactへ適用しません。

review済み環境でvisual baselineを比較する場合は`PLAYWRIGHT_VISUAL_REGRESSION=1`を設定します。
意図した画面変更を目視確認した後だけ、`scripts\run-e2e.ps1 -UpdateSnapshots`でDocker内と
同じLinuxブラウザ環境のbaselineを更新します。通常の機能E2Eでは環境差による誤検知を
避けるためvisual testだけをskipします。
