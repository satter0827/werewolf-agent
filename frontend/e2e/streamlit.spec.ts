import AxeBuilder from "@axe-core/playwright";

import { expect, test } from "./fixtures";

test.use({ baseURL: process.env.PLAYWRIGHT_STREAMLIT_URL ?? "http://streamlit:8501" });

test("Streamlit exposes the same game setup capability through the API", async ({
  page,
}, testInfo) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Werewolf Agent/i })).toBeVisible();
  await expect(page.locator("body")).not.toContainText(/MOC|mock|provider|model|token/i);

  const results = await new AxeBuilder({ page })
    // Streamlit owns the increment/decrement buttons and does not expose a
    // stable hook for application-level accessible names.
    .exclude('[data-testid="stNumberInputStepDown"]')
    .exclude('[data-testid="stNumberInputStepUp"]')
    .analyze();
  expect(
    results.violations.filter(
      (violation) =>
        (violation.impact === "critical" || violation.impact === "serious") &&
        !(
          violation.id === "aria-allowed-attr" &&
          violation.nodes.every((node) => node.target.includes(".stSidebar"))
        ),
    ),
  ).toEqual([]);

  await page.getByRole("button", { name: "新しいゲームを始める" }).click();
  await expect(page.getByText("ゲーム卓", { exact: true })).toBeVisible();
  await expect
    .poll(() =>
      page.evaluate(() =>
        Math.max(
          window.scrollY,
          document.scrollingElement?.scrollTop ?? 0,
          document.querySelector('[data-testid="stAppViewContainer"]')?.scrollTop ?? 0,
          document.querySelector('[data-testid="stMain"]')?.scrollTop ?? 0,
        ),
      ),
    )
    .toBe(0);
  await expect(page.locator("body")).not.toContainText(/provider|model|token/i);
  await page.screenshot({
    path: testInfo.outputPath(`streamlit-gameplay-${testInfo.project.name}.png`),
    fullPage: true,
  });
});

test("Streamlit observer mode uses only public API data", async ({ page }, testInfo) => {
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
  const observerNavigation = page.getByRole("button", { name: /観戦/ });
  if (testInfo.project.name === "mobile") {
    await observerNavigation.evaluate((element) => (element as HTMLButtonElement).click());
  } else {
    await observerNavigation.click();
  }
  await expect(page.getByRole("heading", { name: "観戦開始設定" })).toBeVisible();
  await page.getByRole("button", { name: "観戦を始める" }).click();

  await expect(page.getByText("ゲーム卓", { exact: true })).toBeVisible();
  await expect(page.getByText("観戦モード", { exact: true }).first()).toBeVisible();
  expect(administratorRequests).toEqual([]);
  expect(privateObservationRequests).toEqual([]);
  await page.screenshot({
    path: testInfo.outputPath(`streamlit-observer-${testInfo.project.name}.png`),
    fullPage: true,
  });
});

test("Streamlit records and preferences are reviewable", async ({ page }, testInfo) => {
  await page.goto("/");
  const records = page.getByRole("button", { name: "記録", exact: true }).first();
  if (testInfo.project.name === "mobile") {
    await records.evaluate((element) => (element as HTMLButtonElement).click());
  } else {
    await records.click();
  }
  await expect(page.getByRole("heading", { name: "ゲーム記録" })).toBeVisible();
  await expect(
    page.getByTestId("stMain").getByText("記録はまだありません。", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath(`streamlit-records-${testInfo.project.name}.png`),
    fullPage: true,
  });

  const preferences = page.getByRole("button", { name: "表示設定", exact: true }).first();
  if (testInfo.project.name === "mobile") {
    await preferences.evaluate((element) => (element as HTMLButtonElement).click());
  } else {
    await preferences.click();
  }
  await expect(page.getByRole("heading", { name: "表示設定" })).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath(`streamlit-preferences-${testInfo.project.name}.png`),
    fullPage: true,
  });
});
