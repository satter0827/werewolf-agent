import { afterEach, describe, expect, it, vi } from "vitest";

import { browserConfigError, readBrowserConfig } from "./config";

describe("frontend Supabase configuration", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("reports missing required Vite Supabase env before client creation", () => {
    vi.stubEnv("VITE_SUPABASE_URL", "");
    vi.stubEnv("VITE_SUPABASE_PUBLISHABLE_KEY", "");

    vi.stubEnv("VITE_WEREWOLF_API_URL", "");
    const error = browserConfigError();

    expect(error?.message).toContain("VITE_SUPABASE_URL");
    expect(error?.message).toContain("VITE_SUPABASE_PUBLISHABLE_KEY");
    expect(() => readBrowserConfig()).toThrow("VITE_WEREWOLF_API_URL");
  });

  it("reads required Vite Supabase env without fallback aliases", () => {
    vi.stubEnv("VITE_SUPABASE_URL", "http://127.0.0.1:54321");
    vi.stubEnv("VITE_SUPABASE_PUBLISHABLE_KEY", "publishable-test");
    vi.stubEnv("VITE_WEREWOLF_API_URL", "http://127.0.0.1:8000");

    expect(browserConfigError()).toBeNull();
    expect(readBrowserConfig()).toEqual({
      apiUrl: "http://127.0.0.1:8000",
      supabasePublishableKey: "publishable-test",
      supabaseUrl: "http://127.0.0.1:54321",
    });
  });
});
