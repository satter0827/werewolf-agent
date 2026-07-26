import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

import type { APIRequestContext, APIResponse, Page } from "@playwright/test";

import { expect, test } from "./fixtures";

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

type TimelineResponse = { items: Array<{ sequence: number }> };

async function responseJson<T>(response: APIResponse): Promise<T> {
  if (!response.ok()) throw new Error(`${response.status()} ${await response.text()}`);
  return (await response.json()) as T;
}

async function waitForOperation(
  request: APIRequestContext,
  apiUrl: string,
  token: string,
  operation: Operation,
  networkEvents: Array<{ method: string; status: number; url: string }>,
): Promise<Operation> {
  const deadline = Date.now() + 1_200_000;
  let current = operation;
  while (current.status === "queued" || current.status === "running") {
    if (Date.now() >= deadline) throw new Error("Local LLM operation timed out");
    await new Promise((resolve) => setTimeout(resolve, 500));
    const url = `${apiUrl}/api/v1/operations/${current.operation_id}`;
    let response: APIResponse;
    try {
      response = await request.get(url, { headers: { Authorization: `Bearer ${token}` } });
    } catch (error) {
      if (error instanceof Error && /socket hang up|ECONNRESET|ECONNREFUSED/i.test(error.message))
        continue;
      throw error;
    }
    networkEvents.push({ method: "GET", status: response.status(), url });
    if (response.status() >= 500) continue;
    current = await responseJson<Operation>(response);
  }
  if (current.status === "failed") throw new Error(current.error?.detail ?? "Operation failed");
  return current;
}

async function postOperation(
  request: APIRequestContext,
  url: string,
  token: string,
  body: object,
  networkEvents: Array<{ method: string; status: number; url: string }>,
): Promise<Operation> {
  const response = await request.post(url, {
    data: body,
    headers: {
      Authorization: `Bearer ${token}`,
      "Idempotency-Key": crypto.randomUUID(),
    },
  });
  networkEvents.push({ method: "POST", status: response.status(), url });
  return responseJson<Operation>(response);
}

async function getGame(
  request: APIRequestContext,
  apiUrl: string,
  token: string,
  gameId: string,
  networkEvents: Array<{ method: string; status: number; url: string }>,
): Promise<GameResponse> {
  const url = `${apiUrl}/api/v1/games/${gameId}`;
  const response = await request.get(url, { headers: { Authorization: `Bearer ${token}` } });
  networkEvents.push({ method: "GET", status: response.status(), url });
  return responseJson<GameResponse>(response);
}

async function openStreamlitRecord(
  page: Page,
  streamlitUrl: string,
  email: string,
  password: string,
): Promise<void> {
  await page.goto(streamlitUrl);
  await page.getByText("ログイン", { exact: true }).first().click();
  await page.getByLabel("メールアドレス").fill(email);
  await page.getByLabel("パスワード").fill(password);
  await page.getByRole("button", { name: "ログイン", exact: true }).last().click();
  await expect(page.getByText(email)).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "記録を開く", exact: true }).click();
  await expect(page.getByText("ゲーム卓", { exact: true })).toBeVisible();
  await expect(page.getByText("公開タイムライン", { exact: true }).first()).toBeVisible();
}

async function captureStreamlitRecord(
  owner: Page,
  streamlitUrl: string,
  email: string,
  password: string,
  screenshotPath: string,
  requiredText?: string,
): Promise<void> {
  const page = await owner.context().newPage();
  try {
    await openStreamlitRecord(page, streamlitUrl, email, password);
    if (requiredText)
      await expect(page.getByText(requiredText, { exact: true })).toBeVisible({ timeout: 30_000 });
    await page.screenshot({ path: screenshotPath, fullPage: true });
  } finally {
    await page.close();
  }
}

test("@local-llm Streamlit displays one Local LLM game", async ({ page, request }) => {
  test.skip(process.env.PLAYWRIGHT_LOCAL_LLM !== "1", "Explicit Local LLM review only");
  test.skip(test.info().project.name !== "desktop", "Local LLM review uses one sequential game");
  test.setTimeout(3_600_000);

  const apiUrl = process.env.PLAYWRIGHT_API_URL ?? "http://api:8000";
  const email = process.env.PLAYWRIGHT_LOCAL_EMAIL;
  const password = process.env.PLAYWRIGHT_LOCAL_PASSWORD;
  const screenshotDir = process.env.PLAYWRIGHT_SCREENSHOT_DIR;
  const streamlitUrl = process.env.PLAYWRIGHT_STREAMLIT_URL ?? "http://streamlit:8501";
  const supabaseUrl = process.env.PLAYWRIGHT_SUPABASE_URL;
  const supabaseKey = process.env.PLAYWRIGHT_SUPABASE_PUBLISHABLE_KEY;
  expect(email).toBeTruthy();
  expect(password).toBeTruthy();
  expect(screenshotDir).toBeTruthy();
  expect(supabaseUrl).toBeTruthy();
  expect(supabaseKey).toBeTruthy();
  await mkdir(screenshotDir!, { recursive: true });

  const consoleEvents: Array<{ text: string; type: string }> = [];
  const networkEvents: Array<{ method: string; status: number; url: string }> = [];
  const expectedErrorPages = new WeakSet<Page>();
  const observePage = (observedPage: Page): void => {
    observedPage.on("console", (message) => {
      if (!expectedErrorPages.has(observedPage))
        consoleEvents.push({ text: message.text(), type: message.type() });
    });
    observedPage.on("response", (response) =>
      networkEvents.push({
        method: response.request().method(),
        status: response.status(),
        url: response.url(),
      }),
    );
  };
  observePage(page);
  page.context().on("page", observePage);

  const authUrl = `${supabaseUrl}/auth/v1/token?grant_type=password`;
  const authResponse = await request.post(authUrl, {
    data: { email, password },
    headers: { apikey: supabaseKey! },
  });
  networkEvents.push({ method: "POST", status: authResponse.status(), url: authUrl });
  const auth = await responseJson<{ access_token: string }>(authResponse);
  const token = auth.access_token;

  const create = await postOperation(
    request,
    `${apiUrl}/api/v1/games`,
    token,
    {
      manual_player_id: null,
      narration_mode: "standard",
      seed: 7,
      setup: { mode: "preset", preset_id: "standard_6" },
    },
    networkEvents,
  );
  const created = await waitForOperation(request, apiUrl, token, create, networkEvents);
  const gameId = String(
    (created.result as GameResponse | null)?.game_id ?? created.result?.game_id,
  );
  expect(gameId).not.toBe("");

  await openStreamlitRecord(page, streamlitUrl, email!, password!);
  await page.screenshot({
    path: path.join(screenshotDir!, "streamlit-created.png"),
    fullPage: true,
  });

  let game = await getGame(request, apiUrl, token, gameId, networkEvents);
  for (let step = 0; step < 64 && game.state.status !== "completed"; step += 1) {
    const advance = await postOperation(
      request,
      `${apiUrl}/api/v1/games/${gameId}/advance`,
      token,
      { expected_version: game.state.version },
      networkEvents,
    );
    await waitForOperation(request, apiUrl, token, advance, networkEvents);
    game = await getGame(request, apiUrl, token, gameId, networkEvents);
    if (step === 0) {
      await captureStreamlitRecord(
        page,
        streamlitUrl,
        email!,
        password!,
        path.join(screenshotDir!, "streamlit-progress.png"),
      );
    }
  }
  expect(game.state.status).toBe("completed");
  await captureStreamlitRecord(
    page,
    streamlitUrl,
    email!,
    password!,
    path.join(screenshotDir!, "streamlit-finished.png"),
    "結果サマリー",
  );

  const errorPage = await page.context().newPage();
  expectedErrorPages.add(errorPage);
  await errorPage.goto(streamlitUrl);
  await errorPage.getByText("ログイン", { exact: true }).first().click();
  await errorPage.getByLabel("メールアドレス").fill(email!);
  await errorPage.getByLabel("パスワード").fill("invalid-local-review-password");
  await errorPage.getByRole("button", { name: "ログイン", exact: true }).last().click();
  await expect(errorPage.locator('[data-testid="stAlert"]')).toBeVisible();
  await errorPage.screenshot({
    path: path.join(screenshotDir!, "streamlit-error.png"),
    fullPage: true,
  });
  await errorPage.close();

  const timelineUrl = `${apiUrl}/api/v1/games/${gameId}/timeline?after=0&limit=100`;
  const timelineResponse = await request.get(timelineUrl, {
    headers: { Authorization: `Bearer ${token}` },
  });
  networkEvents.push({ method: "GET", status: timelineResponse.status(), url: timelineUrl });
  const timeline = await responseJson<TimelineResponse>(timelineResponse);
  expect(timeline.items.length).toBeGreaterThan(0);
  expect(networkEvents.some((event) => /:1234(?:\/|$)/.test(event.url))).toBe(false);
  expect(consoleEvents.filter((event) => event.type === "error")).toEqual([]);
  await writeFile(
    path.join(screenshotDir!, "..", "network.json"),
    JSON.stringify(networkEvents, null, 2),
    "utf8",
  );
  await writeFile(
    path.join(screenshotDir!, "..", "console.json"),
    JSON.stringify(consoleEvents, null, 2),
    "utf8",
  );
  await writeFile(
    path.join(screenshotDir!, "..", "local-ui-result.json"),
    JSON.stringify(
      {
        game_id: gameId,
        api_status: game.state.status,
        dom_status: "completed",
        api_state: game,
        api_timeline: timeline,
      },
      null,
      2,
    ),
    "utf8",
  );
});
