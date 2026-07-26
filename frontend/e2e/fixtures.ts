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
  page: async ({ page, request }, use) => {
    const expectedInstance = process.env.PLAYWRIGHT_EXPECTED_INSTANCE_ID;
    expect(expectedInstance, "E2E対象instance IDが設定されていません").toBeTruthy();
    const apiUrl = process.env.PLAYWRIGHT_API_URL ?? "http://127.0.0.1:8000";
    const healthResponse = await request.get(`${apiUrl}/health`);
    expect(healthResponse.ok()).toBeTruthy();
    const health = await healthResponse.json();
    expect(health.instance_id).toBe(expectedInstance);
    expect(health.started_at).toMatch(/^\d{4}-\d{2}-\d{2}T/);
    expect(health.config_fingerprint).toMatch(/^[a-f0-9]{64}$/);

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
