import AxeBuilder from "@axe-core/playwright";

import { sampleNow, sampleScreenSource } from "../src/test/gameSamples";
import { expect, test } from "./fixtures";

test("runtime config, DOM attributes, and computed theme agree", async ({
  page,
  request,
}, testInfo) => {
  const apiUrl = process.env.PLAYWRIGHT_API_URL ?? "http://127.0.0.1:8000";
  const configResponse = await request.get(`${apiUrl}/api/v1/config`);
  expect(configResponse.ok()).toBeTruthy();
  const runtime = await configResponse.json();

  await page.goto("/");
  const app = page.locator(".wa-app");
  await expect(app).toHaveAttribute("data-contract-version", runtime.contract_version);
  await expect(app).toHaveAttribute("data-config-revision", runtime.config_revision);
  await expect(app).toHaveAttribute("data-theme-id", runtime.ui.theme_id);
  await expect(app).toHaveAttribute("data-motion", runtime.ui.motion);
  await expect(app).toHaveAttribute(
    "data-compact-layout",
    String((await page.viewportSize())!.width <= runtime.ui.desktop_breakpoint),
  );
  await expect(app).toHaveAttribute("data-view-mode", "setup");
  await expect(app).toHaveAttribute("data-operation-status", "succeeded");

  const styles = await app.evaluate((element) => {
    const computed = getComputedStyle(element);
    return {
      breakpoint: computed.getPropertyValue("--wa-desktop-breakpoint").trim(),
      color: computed.color,
      spacing: computed.getPropertyValue("--wa-space").trim(),
    };
  });
  expect(styles.color).not.toBe("");
  expect(styles.breakpoint).toBe(`${runtime.ui.desktop_breakpoint}px`);
  expect(styles.spacing).toBe(`${runtime.ui.spacing_unit}px`);
  await page.screenshot({
    path: testInfo.outputPath(`${testInfo.project.name}.png`),
    fullPage: true,
  });
});

test("setup and keyboard flow have no serious accessibility violations", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator(".wa-app")).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(page.locator(":focus-visible")).toBeVisible();

  const results = await new AxeBuilder({ page }).analyze();
  expect(
    results.violations.filter(
      (violation) => violation.impact === "critical" || violation.impact === "serious",
    ),
  ).toEqual([]);
});

test("action constraint agrees with public runtime config", async ({ page, request }) => {
  const apiUrl = process.env.PLAYWRIGHT_API_URL ?? "http://127.0.0.1:8000";
  const runtime = await (await request.get(`${apiUrl}/api/v1/config`)).json();

  await page.goto("/");
  await expect(page.locator(".wa-app")).toHaveAttribute(
    "data-message-max-chars",
    String(runtime.limits.message_max_chars),
  );
});

test("gameplay screen is reviewable on each viewport", async ({ page }, testInfo) => {
  await page.goto("/");
  await expect(page.locator(".wa-app")).toBeVisible();
  await page.getByRole("button", { name: "この村で始める" }).click();
  await expect(page.locator(".wa-app")).toHaveAttribute("data-view-mode", "play");
  if (testInfo.project.name === "mobile") {
    const actionArea = page.locator(".wa-command-zone");
    const position = await actionArea.evaluate((element) => getComputedStyle(element).position);
    expect(position).toBe("sticky");
  }
  await page.screenshot({
    path: testInfo.outputPath(`react-gameplay-${testInfo.project.name}.png`),
    fullPage: true,
  });
});

test("loading and error states leave visual evidence", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "representative state capture");
  let releaseConfig: (() => void) | undefined;
  const configReleased = new Promise<void>((resolve) => {
    releaseConfig = resolve;
  });
  await page.route("**/api/v1/config", async (route) => {
    await configReleased;
    await route.continue();
  });
  await page.goto("/");
  await expect(page.getByText("村の夜明けを準備しています")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("react-loading-desktop.png"), fullPage: true });
  releaseConfig?.();
  await expect(page.locator(".wa-app")).toBeVisible();

  await page.unroute("**/api/v1/config");
  await page.route("**/api/v1/config", (route) => route.abort("failed"));
  await page.reload();
  await expect(page.getByRole("alert")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("react-error-desktop.png"), fullPage: true });
});

test("observer game creation uses only public API data", async ({ page }, testInfo) => {
  const administratorRequests: string[] = [];
  const privateObservationRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/v1/admin")) {
      administratorRequests.push(request.url());
    }
    if (request.url().includes("/observation/")) {
      privateObservationRequests.push(request.url());
    }
  });

  await page.goto("/");
  await page.getByLabel("参加方法").selectOption("");
  await page.getByRole("button", { name: "観戦を始める" }).click();

  await expect(page.locator(".wa-app")).toHaveAttribute("data-view-mode", "observe");
  await expect(page.getByRole("heading", { name: "公開された記録" })).toBeVisible();
  expect(administratorRequests).toEqual([]);
  expect(privateObservationRequests).toEqual([]);
  await page.screenshot({
    path: testInfo.outputPath(`react-observer-${testInfo.project.name}.png`),
    fullPage: true,
  });
});

test("empty records are reviewable on each viewport", async ({ page }, testInfo) => {
  await page.route("**/api/v1/games?*", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ games: [], next_offset: null }),
    }),
  );

  await page.goto("/");
  await page.getByRole("button", { name: "記録", exact: true }).click();
  await expect(page.getByRole("heading", { name: "語り部の本棚" })).toBeVisible();
  await expect(page.locator(".wa-record-row")).toHaveCount(0);
  await page.screenshot({
    path: testInfo.outputPath(`react-records-empty-${testInfo.project.name}.png`),
    fullPage: true,
  });
});

test("completed game is reviewable and has no progress action", async ({ page }, testInfo) => {
  const finished = sampleScreenSource();
  finished.state = {
    ...finished.state,
    game_id: "completed-game",
    status: "completed",
    phase: "finished",
    day: 3,
    version: 8,
    alive_player_ids: finished.state.players.slice(0, 3).map((player) => player.id),
    eliminated_player_ids: finished.state.players.slice(3).map((player) => player.id),
    winner: "villagers",
  };
  finished.timeline = {
    game_id: "completed-game",
    next_after: 3,
    items: [
      ...finished.timeline.items,
      {
        sequence: 3,
        event_sequence: 3,
        version: 8,
        phase: "finished",
        day: 3,
        actor_id: null,
        event_type: "game_finished",
        narration: "村人たちは長い夜を越えました。",
        payload: { winner: "villagers" },
        occurred_at: sampleNow,
      },
    ],
  };
  finished.observation = null;
  await page.route("**/api/v1/games?*", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        games: [
          {
            alive_count: 3,
            completed_at: sampleNow,
            created_at: sampleNow,
            day: 3,
            game_id: "completed-game",
            phase: "finished",
            player_count: 6,
            seed: 17,
            status: "completed",
            step_count: 8,
            turn_count: 20,
            updated_at: sampleNow,
            version: 8,
            winner: "villagers",
          },
        ],
        next_offset: null,
      }),
    }),
  );
  await page.route("**/api/v1/games/completed-game/timeline?*", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(finished.timeline) }),
  );
  await page.route("**/api/v1/games/completed-game", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ game_id: "completed-game", state: finished.state }),
    }),
  );

  await page.goto("/");
  await page.getByRole("button", { name: "記録", exact: true }).click();
  await page.getByRole("button", { name: "結果を見る" }).click();
  await expect(page.locator(".wa-app")).toHaveAttribute("data-view-mode", "observe");
  await expect(page.getByText("村人陣営の勝利")).toBeVisible();
  await expect(page.getByRole("button", { name: "進める" })).toHaveCount(0);
  await page.screenshot({
    path: testInfo.outputPath(`react-completed-${testInfo.project.name}.png`),
    fullPage: true,
  });
});
