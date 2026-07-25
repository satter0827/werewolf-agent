# Streamlit Browser QA

Streamlit 画面を後から AI が再検証するための handoff です。

## 目的

- Streamlit が実ブラウザで表示できることを確認する
- `新しいゲームを始める` から `ゲーム卓`、`公開タイムライン`、`あなたの手番` まで到達することを確認する
- desktop / mobile のスクリーンショットを残す
- console error / warning を確認する

## 起動

VS Code の `launch.json` は `${workspaceFolder}` 起点です。ブランチ名や worktree の絶対 path は指定しません。VS Code で開いている checkout の現在ブランチがそのまま起動対象です。
`App: Streamlit, API, and Worker`を起動します。preflightがDocker、Supabase local stack、
migration、`doctor`を確認し、起動後のE2Eが`setup-options`を確認します。運用ログは`.werewolf-agent/logs`、
品質browser成果物は`.werewolf-agent/quality`配下を使います。

別terminalで手動起動する場合は、先に`python -m scripts.supabase preflight`を実行し、
API、worker、Streamlitを各console entrypointから起動します。

```bash
uv run --no-sync --group dev --extra streamlit streamlit run src/werewolf_agent/clients/streamlit/app.py --server.address 127.0.0.1 --server.port 8766 --server.headless true
```

Supabase worker:

```bash
supabase migration up
uv run --no-sync --group dev --extra worker werewolf-agent-worker run
```

HTTP smoke:

```bash
uv run --no-sync --group dev --extra streamlit python -c "import httpx; print(httpx.get('http://127.0.0.1:8766', timeout=5).status_code)"
```

## Browser plugin

Codex で Browser plugin がある場合でも、直接の Browser tool が一覧に出ないことがあります。
その場合は `node_repl` の `js` tool から Browser runtime を初期化します。
`Browser tool がない` と判断する前に、この経路を試してください。

```js
if (!globalThis.agent) {
  const { setupBrowserRuntime } = await import(
    "C:/Users/brts5/.codex/plugins/cache/openai-bundled/browser/26.519.81530/scripts/browser-client.mjs"
  );
  await setupBrowserRuntime({ globals: globalThis });
}
if (!globalThis.browser) {
  globalThis.browser = await agent.browsers.get("iab");
}
await browser.nameSession("Streamlit UI QA");
if (typeof tab === "undefined" || !globalThis.tab) {
  globalThis.tab = await browser.tabs.new();
}
```

plugin version が変わった場合は、Browser skill の `scripts/browser-client.mjs` を探し、絶対 path で import します。

## desktop 確認

```js
await tab.goto("http://127.0.0.1:8766");
await tab.playwright.waitForLoadState({ state: "load", timeoutMs: 30000 });
await tab.playwright.waitForTimeout(3000);

const snapshot = await tab.playwright.domSnapshot();
const required = ["Werewolf Agent", "プレイ", "観戦", "設定", "新しいゲームを始める"];
console.log(required.map((text) => [text, snapshot.includes(text)]));
console.log(await tab.dev.logs({ levels: ["error", "warn"], limit: 50 }));
```

`新しいゲームを始める` を押して playable state を確認します。

```js
const startButton = tab.playwright.getByRole("button", { name: "新しいゲームを始める", exact: true });
if ((await startButton.count()) !== 1) {
  throw new Error("start button must be unique");
}
await startButton.click({ timeoutMs: 10000 });
await tab.playwright.waitForTimeout(5000);

const afterCreate = await tab.playwright.domSnapshot();
const playable = ["ゲーム卓", "公開タイムライン", "あなたの手番", "現在のフェーズ", "現在の手番"];
console.log(playable.map((text) => [text, afterCreate.includes(text)]));
console.log(await tab.dev.logs({ levels: ["error", "warn"], limit: 50 }));
```

## mobile 確認

mobile 幅でも初回の `新しいゲームを始める` はメイン画面から押せます。sidebar は補助導線としてだけ確認します。

```js
const viewport = await browser.capabilities.get("viewport");
await viewport.set({ width: 390, height: 844 });
await tab.reload();
await tab.playwright.waitForLoadState({ state: "load", timeoutMs: 30000 });
await tab.playwright.waitForTimeout(3000);

const openSidebar = tab.playwright.getByRole("button", {
  name: "keyboard_double_arrow_right",
  exact: true,
});
if ((await openSidebar.count()) === 1 && (await openSidebar.isVisible())) {
  await openSidebar.click({ timeoutMs: 10000 });
  await tab.playwright.waitForTimeout(1000);
}

const mobileStartButton = tab.playwright.getByRole("button", {
  name: "新しいゲームを始める",
  exact: true,
});
if ((await mobileStartButton.count()) !== 1) {
  throw new Error("mobile start button must be unique");
}
await mobileStartButton.click({ timeoutMs: 10000 });
await tab.playwright.waitForTimeout(5000);

const mobileAfterCreate = await tab.playwright.domSnapshot();
console.log(["ゲーム卓", "公開タイムライン", "あなたの手番", "現在のフェーズ"].map(
  (text) => [text, mobileAfterCreate.includes(text)]
));
console.log(await tab.dev.logs({ levels: ["error", "warn"], limit: 50 }));
await viewport.reset();
```

## スクリーンショット

QA screenshot は repository 配下の cache に残しません。保存が必要な画像は
`docs/notes/assets/streamlit-ui/` に置きます。

今回移動済みの画像:

- `docs/notes/assets/streamlit-ui/07-qa-console-desktop.png`
- `docs/notes/assets/streamlit-ui/08-qa-observer-desktop.png`
- `docs/notes/assets/streamlit-ui/09-qa-observer-mobile.png`
- `docs/notes/assets/streamlit-ui/10-qa-zero-base-review.png`

一時ファイルとして保存する場合は `%TEMP%\werewolf-agent\qa\` を使い、採用する画像は docs 配下へ移します。

## 今回の確認結果

- 実行日: 2026-05-29
- Streamlit: `http://127.0.0.1:8766`
- desktop: `新しいゲームを始める` から A案画面まで到達
- desktop: `ゲーム卓`、`あなたの手番`、`公開タイムライン` を A案構成で確認
- mobile: メイン画面から game を作成した後、上部ステータス、`ゲーム卓`、`あなたの手番`、`公開タイムライン` が縦積みで DOM に存在することを確認
- raw HTML 表示: なし
- console error / warning: 確認開始時刻以降はなし
- Browser output に desktop / mobile の screenshot を表示できることを確認
