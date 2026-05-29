# Streamlit Browser QA

Streamlit 画面を後から AI が再検証するための handoff です。

## 目的

- Streamlit が実ブラウザで表示できることを確認する
- `ゲームを始める` から `ゲーム卓`、`これまでの流れ`、`あなたの手番` まで到達することを確認する
- desktop / mobile のスクリーンショットを残す
- console error / warning を確認する

## 起動

別 terminal で API と Streamlit を起動します。

```bash
uv run --extra api alembic upgrade head
uv run --extra api uvicorn werewolf_agent.interface.api.app:create_app --factory --host 127.0.0.1 --port 8000
uv run --extra streamlit streamlit run backend/src/werewolf_agent/interface/entrypoint/streamlit/app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true
```

HTTP smoke:

```bash
uv run python -c "import httpx; print(httpx.get('http://127.0.0.1:8000/api/v1/health', timeout=5).json()); print(httpx.get('http://127.0.0.1:8501', timeout=5).status_code)"
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
await tab.goto("http://127.0.0.1:8501");
await tab.playwright.waitForLoadState({ state: "load", timeoutMs: 30000 });
await tab.playwright.waitForTimeout(3000);

const snapshot = await tab.playwright.domSnapshot();
const required = ["Werewolf Agent", "API 接続", "新しいゲーム", "ゲームを始める", "現在のゲーム"];
console.log(required.map((text) => [text, snapshot.includes(text)]));
console.log(await tab.dev.logs({ levels: ["error", "warn"], limit: 50 }));
```

`ゲームを始める` を押して playable state を確認します。

```js
const startButton = tab.playwright.getByRole("button", { name: "ゲームを始める", exact: true });
if ((await startButton.count()) !== 1) {
  throw new Error("start button must be unique");
}
await startButton.click({ timeoutMs: 10000 });
await tab.playwright.waitForTimeout(5000);

const afterCreate = await tab.playwright.domSnapshot();
const playable = ["ゲーム卓", "これまでの流れ", "あなたの手番", "現在のフェーズ", "現在の手番"];
console.log(playable.map((text) => [text, afterCreate.includes(text)]));
console.log(await tab.dev.logs({ levels: ["error", "warn"], limit: 50 }));
```

## mobile 確認

Streamlit は mobile 幅で sidebar が閉じるため、`ゲームを始める` を押す前に sidebar を開きます。

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
  name: "ゲームを始める",
  exact: true,
});
if ((await mobileStartButton.count()) !== 1) {
  throw new Error("mobile start button must be unique");
}
await mobileStartButton.click({ timeoutMs: 10000 });
await tab.playwright.waitForTimeout(5000);

const mobileAfterCreate = await tab.playwright.domSnapshot();
console.log(["ゲーム卓", "これまでの流れ", "あなたの手番", "現在のフェーズ"].map(
  (text) => [text, mobileAfterCreate.includes(text)]
));
console.log(await tab.dev.logs({ levels: ["error", "warn"], limit: 50 }));
await viewport.reset();
```

## スクリーンショット

QA screenshot は repo 管理対象にせず、`.werewolf-agent/qa/` に保存します。

```js
const fs = await import("node:fs/promises");
await fs.mkdir(".werewolf-agent/qa", { recursive: true });
await fs.writeFile(
  ".werewolf-agent/qa/streamlit-browser-qa-desktop.png",
  Buffer.from(await tab.screenshot({ fullPage: false }))
);
```

mobile は viewport を `390x844` にしてから
`.werewolf-agent/qa/streamlit-browser-qa-mobile.png` に保存します。

## 今回の確認結果

- 実行日: 2026-05-29
- API: `http://127.0.0.1:8765/api/v1`
- Streamlit: `http://127.0.0.1:8766`
- desktop: `ゲームを始める` から playable state まで到達
- mobile: sidebar を開いて `ゲームを始める` から playable state まで到達
- console error / warning: なし
- Browser output に desktop / mobile の screenshot を表示できることを確認
- `tab.screenshot({ path })` は成功を返しても、この環境では PowerShell 側から保存ファイルを確認できない場合がある
- host filesystem 上の保存が必要な場合は、Browser output の画像取得後に app 側の artifact 保存経路を使う
