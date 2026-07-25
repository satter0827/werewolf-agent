import { describe, expect, it, vi } from "vitest";

import { AuthClient } from "./AuthClient";

type AuthDependency = ConstructorParameters<typeof AuthClient>[0];

describe("AuthClient access token", () => {
  it("reuses the current authenticated or anonymous session", async () => {
    const signInAnonymously = vi.fn();
    const client = new AuthClient({
      auth: {
        getSession: vi.fn().mockResolvedValue({
          data: { session: { access_token: "current-token" } },
          error: null,
        }),
        signInAnonymously,
      },
    } as unknown as AuthDependency);

    await expect(client.accessToken()).resolves.toBe("current-token");
    expect(signInAnonymously).not.toHaveBeenCalled();
  });

  it("starts an anonymous session when no session exists", async () => {
    const client = new AuthClient({
      auth: {
        getSession: vi.fn().mockResolvedValue({
          data: { session: null },
          error: null,
        }),
        signInAnonymously: vi.fn().mockResolvedValue({
          data: { session: { access_token: "guest-token" } },
          error: null,
        }),
      },
    } as unknown as AuthDependency);

    await expect(client.accessToken()).resolves.toBe("guest-token");
  });
});
