import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("runtime config, DOM attributes, and computed theme agree", async ({ page, request }) => {
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

test("mobile layout presents the action area as a bottom sheet", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "mobile", "mobile-only layout assertion");
  await page.goto("/");
  await expect(page.locator(".wa-app")).toBeVisible();
  await page.getByRole("button", { name: "この村で始める" }).click();
  await expect(page.locator(".wa-app")).toHaveAttribute("data-view-mode", "play");
  const actionArea = page.locator(".wa-command-zone");
  const position = await actionArea.evaluate((element) => getComputedStyle(element).position);
  expect(position).toBe("sticky");
});

test("observer game creation uses only public API data", async ({ page }) => {
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
});

test("stable setup screen matches the reviewed visual baseline", async ({ page }, testInfo) => {
  test.skip(
    process.env.PLAYWRIGHT_VISUAL_REGRESSION !== "1",
    "visual baselines are updated only in the controlled browser QA environment",
  );
  await page.goto("/");
  await expect(page.locator(".wa-app")).toBeVisible();
  await expect(page).toHaveScreenshot(`setup-${testInfo.project.name}.png`, {
    animations: "disabled",
    fullPage: true,
  });
});
