import type { Client } from "openapi-fetch";
import { describe, expect, it, vi } from "vitest";

import type { paths } from "../generated/api";
import { ApiGameClient, createIdempotencyKey } from "./ApiGameClient";

describe("ApiGameClient", () => {
  it("reads public runtime settings through the generated HTTP client", async () => {
    const api = {
      use: vi.fn(),
      GET: vi.fn().mockResolvedValue({
        data: {
          contract_version: "v1",
          config_revision: "test",
          setup: {
            player_count: { min: 5, max: 8 },
            roles: [],
            default_role_counts: {},
            default_rules: {},
          },
          limits: {
            game_min_players: 5,
            game_max_players: 8,
            message_max_chars: 120,
            game_list_page_size: 20,
            timeline_page_size: 100,
          },
          features: {
            authentication: true,
            paid_llm_for_members: true,
            admin_reveal: true,
            admin_replay: true,
          },
          ui: {
            theme_id: "dawn-table",
            spacing_unit: 4,
            desktop_breakpoint: 980,
            motion: "system",
            default_manual_player_id: "player-1",
            default_setup_seed: "1",
            operation_poll_interval_ms: 250,
            operation_poll_timeout_ms: 60_000,
          },
        },
        error: undefined,
      }),
    } as unknown as Client<paths>;
    const auth = {
      accessToken: vi.fn().mockResolvedValue("access"),
    };
    const client = new ApiGameClient(api, auth);

    const config = await client.getRuntimeConfig();

    expect(config.contract_version).toBe("v1");
    expect(api.GET).toHaveBeenCalledWith("/api/v1/config");
  });

  it("continues polling after a retryable operation status failure", async () => {
    const completed = {
      operation_id: "operation-1",
      operation_type: "create_game",
      status: "succeeded",
      result: { game_id: "game-1" },
    };
    const api = {
      use: vi.fn(),
      POST: vi.fn().mockResolvedValue({
        data: { ...completed, status: "running", result: null },
        error: undefined,
      }),
      GET: vi
        .fn()
        .mockResolvedValueOnce({
          data: {
            ui: { operation_poll_interval_ms: 1, operation_poll_timeout_ms: 1_000 },
          },
          error: undefined,
        })
        .mockResolvedValueOnce({
          data: undefined,
          error: { detail: "temporary", retryable: true },
        })
        .mockResolvedValueOnce({ data: completed, error: undefined }),
    } as unknown as Client<paths>;
    const client = new ApiGameClient(api, {
      accessToken: vi.fn().mockResolvedValue("access"),
    });

    const game = await client.createGame({} as never);

    expect(game).toEqual({ game_id: "game-1" });
    expect(api.GET).toHaveBeenCalledTimes(3);
  });
});

describe("createIdempotencyKey", () => {
  it("uses the native UUID implementation when available", () => {
    const randomUUID = vi.fn(() => "00000000-0000-4000-8000-000000000001" as const);
    const source = {
      getRandomValues: vi.fn(),
      randomUUID,
    } as unknown as Crypto;

    expect(createIdempotencyKey(source)).toBe("00000000-0000-4000-8000-000000000001");
    expect(randomUUID).toHaveBeenCalledOnce();
    expect(source.getRandomValues).not.toHaveBeenCalled();
  });

  it("creates an RFC 4122 UUID when randomUUID is unavailable", () => {
    const source = {
      getRandomValues: (values: Uint8Array) => values,
    } as unknown as Crypto;

    expect(createIdempotencyKey(source)).toBe("00000000-0000-4000-8000-000000000000");
  });
});
