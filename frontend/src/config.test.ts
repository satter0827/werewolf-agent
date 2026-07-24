import { afterEach, describe, expect, it, vi } from "vitest";

import { readSupabaseBrowserConfig, supabaseBrowserConfigError } from "./config";

describe("frontend Supabase configuration", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("reports missing required Vite Supabase env before client creation", () => {
    vi.stubEnv("VITE_SUPABASE_URL", "");
    vi.stubEnv("VITE_SUPABASE_PUBLISHABLE_KEY", "");

    const error = supabaseBrowserConfigError();

    expect(error?.message).toContain("VITE_SUPABASE_URL");
    expect(error?.message).toContain("VITE_SUPABASE_PUBLISHABLE_KEY");
    expect(() => readSupabaseBrowserConfig()).toThrow("VITE_SUPABASE_URL");
  });

  it("reads required Vite Supabase env without fallback aliases", () => {
    vi.stubEnv("VITE_SUPABASE_URL", "http://127.0.0.1:54321");
    vi.stubEnv("VITE_SUPABASE_PUBLISHABLE_KEY", "publishable-test");

    expect(supabaseBrowserConfigError()).toBeNull();
    expect(readSupabaseBrowserConfig()).toEqual({
      publishableKey: "publishable-test",
      url: "http://127.0.0.1:54321",
    });
  });
});
