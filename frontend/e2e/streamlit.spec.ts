import AxeBuilder from "@axe-core/playwright";

import { expect, test } from "./fixtures";

test.use({ baseURL: process.env.PLAYWRIGHT_STREAMLIT_URL ?? "http://streamlit:8501" });

test("Streamlit exposes the same game setup capability through the API", async ({ page }) => {
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
  await expect(page.locator("body")).not.toContainText(/provider|model|token/i);
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
});
