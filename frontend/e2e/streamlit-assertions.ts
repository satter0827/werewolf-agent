import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";

import { expect } from "./fixtures";

export async function assertStreamlitQuality(page: Page): Promise<void> {
  await expect(page.locator("body")).not.toContainText(
    /MOC|mock|provider|model|token|Supabase|DB|API/i,
  );
  await assertNoHorizontalOverflow(page);
  await assertMinimumButtonTargets(page);
  await assertHeadingOrder(page);
  await assertVisibleKeyboardFocus(page);
  await assertNoSeriousAxeViolations(page);
}

export async function assertNoHorizontalOverflow(page: Page): Promise<void> {
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth),
  ).toBeLessThanOrEqual(1);
}

export async function assertMinimumButtonTargets(page: Page): Promise<void> {
  const undersized = await page.locator("button:visible, [role=tab]:visible").evaluateAll((nodes) =>
    nodes
      .map((node) => ({
        height: node.getBoundingClientRect().height,
        text: (node.textContent ?? "").trim(),
        width: node.getBoundingClientRect().width,
      }))
      .filter(({ height, width }) => height < 44 || width < 44),
  );
  expect(undersized, "44px未満の操作対象があります").toEqual([]);
}

export async function assertHeadingOrder(page: Page): Promise<void> {
  const levels = await page
    .locator(
      '[data-testid="stMain"] h1:visible, [data-testid="stMain"] h2:visible, [data-testid="stMain"] h3:visible',
    )
    .evaluateAll((nodes) => nodes.map((node) => Number(node.tagName.slice(1))));
  expect(levels[0]).toBe(1);
  for (let index = 1; index < levels.length; index += 1) {
    expect(levels[index] - levels[index - 1]).toBeLessThanOrEqual(1);
  }
}

export async function assertVisibleKeyboardFocus(page: Page): Promise<void> {
  await page.keyboard.press("Tab");
  await expect(page.locator(":focus-visible"), "keyboard focusが視認できません").toBeVisible();
}

export async function assertNoSeriousAxeViolations(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page })
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
}
