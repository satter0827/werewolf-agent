import { defineConfig, devices } from "@playwright/test";

const artifactRoot = process.env.PLAYWRIGHT_OUTPUT_DIR ?? "../.werewolf-agent/playwright";

export default defineConfig({
  testDir: process.env.PLAYWRIGHT_TEST_DIR ?? "e2e",
  // ReactとStreamlitは同じFake LLM backendと匿名principalを共有する。
  // 状態遷移を競合させず、利用者導線を一つずつ再現する。
  workers: 1,
  outputDir: `${artifactRoot}/test-results`,
  reporter: [
    ["json", { outputFile: `${artifactRoot}/results.json` }],
    ["html", { outputFolder: `${artifactRoot}/html`, open: "never" }],
  ],
  timeout: 45_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:8080",
    trace: process.env.PLAYWRIGHT_LOCAL_LLM === "1" ? "on" : "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "mobile",
      use: { ...devices["Pixel 7"] },
    },
  ],
});
