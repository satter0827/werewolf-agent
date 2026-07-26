import { defineConfig, devices } from "@playwright/test";

const artifactRoot = process.env.PLAYWRIGHT_OUTPUT_DIR ?? "../.werewolf-agent/playwright";

export default defineConfig({
  testDir: process.env.PLAYWRIGHT_TEST_DIR ?? "e2e",
  outputDir: `${artifactRoot}/test-results`,
  reporter: [
    ["json", { outputFile: `${artifactRoot}/results.json` }],
    ["html", { outputFolder: `${artifactRoot}/html`, open: "never" }],
  ],
  timeout: 45_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:8080",
    trace: "retain-on-failure",
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
