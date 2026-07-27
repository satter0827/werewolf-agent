import type { APIRequestContext, APIResponse, Locator, Page } from "@playwright/test";

import { expect, test } from "./fixtures";
import { assertNoHorizontalOverflow, assertStreamlitQuality } from "./streamlit-assertions";

test.use({ baseURL: process.env.PLAYWRIGHT_STREAMLIT_URL ?? "http://streamlit:8501" });

test("Streamlit setup exposes four sections and validation", async ({ page }, testInfo) => {
  await page.goto("/");
  await expect(page.getByText("Werewolf Agent", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "ゲーム開始設定" })).toBeVisible();

  for (const name of ["世界観", "役職", "登場人物", "ルール"]) {
    await expect(page.getByRole("tab", { name })).toBeVisible();
  }
  await page.getByRole("tab", { name: "役職" }).click();
  const villagerCount = page.getByRole("spinbutton", { name: "村人", exact: true });
  await villagerCount.fill("0");
  await villagerCount.press("Tab");
  await expect(page.getByText(/合計人数は .* 人にしてください/)).toBeVisible();

  await assertStreamlitQuality(page);
  await page.screenshot({
    path: testInfo.outputPath(`streamlit-setup-validation-${testInfo.project.name}.png`),
    fullPage: true,
  });
});

test("Streamlit gameplay exposes waiting, speech, target, and progress", async ({
  page,
}, testInfo) => {
  test.setTimeout(120_000);
  await page.goto("/");
  await page.getByRole("tab", { name: "役職" }).click();
  const villagerCount = page.getByRole("spinbutton", { name: "村人", exact: true });
  await villagerCount.fill("2");
  await villagerCount.press("Tab");
  await page.getByRole("button", { name: "新しいゲームを始める" }).click();
  await expect(page.getByRole("heading", { name: "月明かりの卓" })).toBeVisible();
  await expect(page.getByText("ゲーム卓", { exact: true })).toBeVisible();
  await expect(page.locator(".wa-status")).toHaveCount(6);
  await expect(page.locator(".wa-seat")).toHaveCount(5);

  const advance = page.getByRole("button", { name: "1ステップ進める" });
  await expect(advance).toBeVisible({ timeout: 30_000 });
  await advance.focus();
  await page.keyboard.press("Enter");

  const message = page.getByLabel("発言内容");
  await expect(message).toBeVisible({ timeout: 30_000 });
  await message.fill("公開情報を整理して話します。");
  await message.press("Tab");
  const submit = page.getByRole("button", { name: "入力を送信" });
  await expect(submit).toBeEnabled();
  await submit.click();
  await expect(page.locator('[data-testid="stStatusWidget"]')).toHaveCount(1);
  await expect(page.getByLabel("対象を選ぶ")).toBeVisible({ timeout: 30_000 });
  await assertStreamlitQuality(page);
  await page.screenshot({
    path: testInfo.outputPath(`streamlit-gameplay-${testInfo.project.name}.png`),
    fullPage: true,
  });
});

test("Streamlit completed game presents result before timeline", async ({
  page,
  request,
}, testInfo) => {
  test.setTimeout(180_000);
  const apiUrl = process.env.PLAYWRIGHT_API_URL ?? "http://api:8000";
  const credentials = await createAuthenticatedUser(request);
  await createCompletedGame(request, apiUrl, credentials.token);

  await page.goto("/");
  await openSidebarIfNeeded(page);
  const loginSummary = page
    .locator('[data-testid="stExpander"] summary')
    .filter({ hasText: "ログイン" });
  await loginSummary.focus();
  await page.keyboard.press("Enter");
  await page.getByLabel("メールアドレス").fill(credentials.email);
  await page.getByLabel("パスワード").fill(credentials.password);
  const loginButton = page.getByRole("button", { name: "ログイン", exact: true }).last();
  await loginButton.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText(credentials.email)).toBeVisible({ timeout: 30_000 });
  const openRecord = page.getByRole("button", { name: "記録を開く", exact: true });
  await openRecord.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("結果サマリー", { exact: true })).toBeVisible({ timeout: 30_000 });
  const resultBox = await page.getByText("結果サマリー", { exact: true }).boundingBox();
  const timelineBox = await page
    .getByText("公開タイムライン", { exact: true })
    .first()
    .boundingBox();
  expect(resultBox?.y).toBeLessThan(timelineBox?.y ?? 0);
  await expect(page.getByRole("button", { name: "1ステップ進める" })).toHaveCount(0);
  await assertStreamlitQuality(page);
  await page.screenshot({
    path: testInfo.outputPath(`streamlit-gameplay-complete-${testInfo.project.name}.png`),
    fullPage: true,
  });
});

test("Streamlit observer uses public data and normal labeled controls", async ({
  page,
}, testInfo) => {
  const administratorRequests: string[] = [];
  const privateObservationRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/v1/admin")) administratorRequests.push(request.url());
    if (request.url().includes("/observation/")) privateObservationRequests.push(request.url());
  });

  await page.goto("/");
  await openNavigation(page, "観戦");
  await expect(page.getByRole("heading", { name: "観戦開始設定" })).toBeVisible();
  await page.getByRole("button", { name: "観戦を始める" }).click();
  await expect(page.getByText("ゲーム卓", { exact: true })).toBeVisible();
  await expect(page.getByText("観戦モード", { exact: true }).first()).toBeVisible();
  expect(administratorRequests).toEqual([]);
  expect(privateObservationRequests).toEqual([]);
  await assertStreamlitQuality(page);
  await page.screenshot({
    path: testInfo.outputPath(`streamlit-observer-${testInfo.project.name}.png`),
    fullPage: true,
  });
});

test("Streamlit records empty state, settings, and 320px layout remain usable", async ({
  page,
}, testInfo) => {
  await page.goto("/");
  await openNavigation(page, "記録");
  await expect(page.getByRole("heading", { name: "ゲーム記録" })).toBeVisible();
  await expect(page.getByRole("button", { name: "プレイを始める" })).toBeVisible();
  await expect(page.getByRole("button", { name: "観戦を始める" })).toBeVisible();

  await openNavigation(page, "表示設定");
  await expect(page.getByRole("heading", { name: "表示設定" })).toBeVisible();
  for (const name of ["表示", "役職定義", "人物定義"]) {
    await expect(page.getByRole("tab", { name })).toBeVisible();
  }
  await assertStreamlitQuality(page);

  if (testInfo.project.name === "desktop") {
    await page.setViewportSize({ width: 320, height: 844 });
    await assertNoHorizontalOverflow(page);
    await openNavigation(page, "プレイ");
    await expect(page.getByRole("heading", { name: "ゲーム開始設定" })).toBeVisible();
  }
  await page.screenshot({
    path: testInfo.outputPath(`streamlit-settings-${testInfo.project.name}.png`),
    fullPage: true,
  });
});

async function openNavigation(page: Page, label: string): Promise<void> {
  await openSidebarIfNeeded(page);
  const button: Locator = page.getByRole("button", { name: label, exact: true }).first();
  await button.focus();
  await page.keyboard.press("Enter");
}

async function openSidebarIfNeeded(page: Page): Promise<void> {
  const openSidebar = page.getByRole("button", {
    name: /open sidebar|keyboard_double_arrow_right/i,
  });
  if (await openSidebar.isVisible()) {
    await openSidebar.click();
  }
}

type Operation = {
  error?: { detail?: string } | null;
  operation_id: string;
  result?: Record<string, unknown> | null;
  status: "queued" | "running" | "succeeded" | "failed";
};

type GameResponse = {
  game_id: string;
  state: { status: string; version: number };
};

async function responseJson<T>(response: APIResponse): Promise<T> {
  if (!response.ok()) throw new Error(`${response.status()} ${await response.text()}`);
  return (await response.json()) as T;
}

async function waitForOperation(
  request: APIRequestContext,
  apiUrl: string,
  operation: Operation,
  token: string,
): Promise<Operation> {
  let current = operation;
  const deadline = Date.now() + 30_000;
  while (current.status === "queued" || current.status === "running") {
    if (Date.now() >= deadline) throw new Error("Fake LLM operation timed out");
    await new Promise((resolve) => setTimeout(resolve, 250));
    current = await responseJson<Operation>(
      await request.get(`${apiUrl}/api/v1/operations/${current.operation_id}`, {
        headers: { Authorization: `Bearer ${token}` },
      }),
    );
  }
  if (current.status === "failed") throw new Error(current.error?.detail ?? "Operation failed");
  return current;
}

async function postOperation(
  request: APIRequestContext,
  apiUrl: string,
  path: string,
  body: object,
  token: string,
): Promise<Operation> {
  const response = await request.post(`${apiUrl}${path}`, {
    data: body,
    headers: {
      Authorization: `Bearer ${token}`,
      "Idempotency-Key": crypto.randomUUID(),
    },
  });
  return waitForOperation(request, apiUrl, await responseJson<Operation>(response), token);
}

async function createAuthenticatedUser(
  request: APIRequestContext,
): Promise<{ email: string; password: string; token: string }> {
  const supabaseUrl = process.env.PLAYWRIGHT_SUPABASE_URL;
  const publishableKey = process.env.PLAYWRIGHT_SUPABASE_PUBLISHABLE_KEY;
  expect(supabaseUrl).toBeTruthy();
  expect(publishableKey).toBeTruthy();
  const email = `streamlit-e2e-${crypto.randomUUID()}@example.com`;
  const password = `Streamlit-${crypto.randomUUID()}!`;
  const auth = await responseJson<{ access_token: string }>(
    await request.post(`${supabaseUrl}/auth/v1/signup`, {
      data: { email, password },
      headers: { apikey: publishableKey! },
    }),
  );
  return { email, password, token: auth.access_token };
}

async function createCompletedGame(
  request: APIRequestContext,
  apiUrl: string,
  token: string,
): Promise<void> {
  const created = await postOperation(
    request,
    apiUrl,
    "/api/v1/games",
    {
      manual_player_id: null,
      narration_mode: "standard",
      seed: 7,
      setup: { mode: "preset", preset_id: "standard_6" },
    },
    token,
  );
  const gameId = String((created.result as GameResponse | null)?.game_id ?? "");
  expect(gameId).not.toBe("");

  const authHeaders = { Authorization: `Bearer ${token}` };
  let game = await responseJson<GameResponse>(
    await request.get(`${apiUrl}/api/v1/games/${gameId}`, { headers: authHeaders }),
  );
  for (let step = 0; step < 64 && game.state.status !== "completed"; step += 1) {
    await postOperation(
      request,
      apiUrl,
      `/api/v1/games/${gameId}/advance`,
      {
        expected_version: game.state.version,
      },
      token,
    );
    game = await responseJson<GameResponse>(
      await request.get(`${apiUrl}/api/v1/games/${gameId}`, { headers: authHeaders }),
    );
  }
  expect(game.state.status).toBe("completed");
}
