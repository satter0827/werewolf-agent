import { expect, test as base } from "@playwright/test";

const localHosts = new Set([
  "127.0.0.1",
  "::1",
  "api",
  "frontend-e2e",
  "host.docker.internal",
  "localhost",
  "streamlit",
]);

export const test = base.extend({
  page: async ({ page }, use) => {
    const blockedHosts = new Set<string>();
    await page.route("**/*", async (route) => {
      const hostname = new URL(route.request().url()).hostname;
      if (localHosts.has(hostname)) {
        await route.continue();
        return;
      }
      blockedHosts.add(hostname);
      await route.abort("blockedbyclient");
    });

    await use(page);

    expect(
      [...blockedHosts],
      `外部network接続を試行しました: ${[...blockedHosts].join(", ")}`,
    ).toEqual([]);
  },
});

export { expect };
