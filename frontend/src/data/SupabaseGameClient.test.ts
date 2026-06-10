import { describe, expect, it, vi } from "vitest";

import { sampleScreenSource, sampleSetupOptions } from "../test/gameSamples";
import { SupabaseGameClient } from "./SupabaseGameClient";

describe("SupabaseGameClient", () => {
  it("creates one anonymous session when no session is cached", async () => {
    const supabase = new FakeSupabase({ session: null });
    const client = new SupabaseGameClient(supabase.port(), { pollIntervalMs: 1 });

    await Promise.all([client.ensureSession(), client.ensureSession()]);

    expect(supabase.signInAnonymously).toHaveBeenCalledTimes(1);
  });

  it("enqueues create_game and returns worker result payload", async () => {
    const screen = sampleScreenSource();
    const supabase = new FakeSupabase({
      operationRow: {
        request_id: "request-1",
        status: "completed",
        result_payload: {
          game_id: screen.state.game_id,
          state: screen.state,
        },
      },
    });
    const client = new SupabaseGameClient(supabase.port(), { pollIntervalMs: 1 });

    const response = await client.createGame({
      seed: 17,
      scenario_id: "misty-village",
      setup_preset_id: "classic-six",
      role_counts: sampleSetupOptions.default_role_counts,
      manual_player_id: "player-1",
      rules: sampleSetupOptions.default_rules,
    });

    expect(response.game_id).toBe("sample-game");
    expect(supabase.insertedOperations[0]).toMatchObject({
      operation_type: "create_game",
      request_payload: { manual_player_id: "player-1" },
    });
  });

  it("surfaces failed worker operations", async () => {
    const supabase = new FakeSupabase({
      operationRow: {
        request_id: "request-1",
        status: "failed",
        error_payload: { detail: "worker failed" },
      },
    });
    const client = new SupabaseGameClient(supabase.port(), { pollIntervalMs: 1 });

    await expect(
      client.submitAction({
        gameId: "sample-game",
        playerId: "player-1",
        action: { type: "speech", message: "話します" },
      }),
    ).rejects.toThrow("worker failed");
  });

  it("times out when the worker does not finish", async () => {
    const supabase = new FakeSupabase({
      operationRow: { request_id: "request-1", status: "queued" },
    });
    const client = new SupabaseGameClient(supabase.port(), {
      pollIntervalMs: 1,
      pollTimeoutMs: 3,
    });

    await expect(client.advance({ gameId: "sample-game" })).rejects.toThrow(
      "Supabase operation timed out.",
    );
  });

  it("reads setup options and backend-shaped private observation", async () => {
    const screen = sampleScreenSource();
    const supabase = new FakeSupabase({ screen });
    const client = new SupabaseGameClient(supabase.port(), { pollIntervalMs: 1 });

    const setupOptions = await client.getSetupOptions();
    const loadedScreen = await client.getScreen("sample-game", "player-1");

    expect(setupOptions.default_setup_preset_id).toBe("classic-six");
    expect(loadedScreen.observation).toMatchObject({
      game_id: "sample-game",
      player_id: "player-1",
      observation: { available_actions: ["speech"] },
    });
  });
});

type QueryResult<T> = { data: T | null; error: { code?: string; message: string } | null };
type OperationRow = {
  error_payload?: { detail?: string; message?: string } | null;
  request_id: string;
  result_payload?: unknown;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
};

class FakeSupabase {
  readonly insertedOperations: Record<string, unknown>[] = [];
  readonly signInAnonymously = vi.fn(async () => {
    this.session = { access_token: "anonymous" };
    return okSession(this.session);
  });

  private operationRow: OperationRow;
  private screen = sampleScreenSource();
  private session: unknown | null;

  constructor({
    operationRow = { request_id: "request-1", status: "completed", result_payload: {} },
    screen = sampleScreenSource(),
    session = { access_token: "existing" },
  }: {
    operationRow?: OperationRow;
    screen?: ReturnType<typeof sampleScreenSource>;
    session?: unknown | null;
  } = {}) {
    this.operationRow = operationRow;
    this.screen = screen;
    this.session = session;
  }

  port() {
    return {
      auth: {
        getSession: async () => okSession(this.session),
        signInAnonymously: this.signInAnonymously,
      },
      from: (table: string) => new FakeQuery(this, table),
    };
  }

  execute(table: string, filters: Record<string, unknown>, insertBody: unknown): QueryResult<any> {
    if (table === "game_operation_requests" && insertBody) {
      this.insertedOperations.push(insertBody as Record<string, unknown>);
      return ok({ request_id: this.operationRow.request_id, status: "queued" });
    }
    if (table === "game_operation_requests") {
      return ok(this.operationRow);
    }
    if (table === "definition_items") {
      return ok({ payload: sampleSetupOptions });
    }
    if (table === "games") {
      return ok({ public_state: this.screen.state });
    }
    if (table === "game_public_turns") {
      return ok(
        this.screen.timeline.items.map((item) => ({
          ...item,
          game_id: this.screen.state.game_id,
        })),
      );
    }
    if (table === "game_player_observations") {
      if (filters.player_id !== "player-1") {
        return ok(null);
      }
      return ok(this.screen.observation);
    }
    if (table === "game_summaries") {
      return ok([]);
    }
    if (table === "game_reveals") {
      return ok(null);
    }
    return ok(null);
  }
}

class FakeQuery {
  private filters: Record<string, unknown> = {};
  private insertBody: unknown = null;

  constructor(
    private readonly supabase: FakeSupabase,
    private readonly table: string,
  ) {}

  eq(column: string, value: unknown): this {
    this.filters[column] = value;
    return this;
  }

  insert(body: unknown): this {
    this.insertBody = body;
    return this;
  }

  limit(): this {
    return this;
  }

  maybeSingle(): Promise<QueryResult<any>> {
    return Promise.resolve(this.supabase.execute(this.table, this.filters, this.insertBody));
  }

  order(): this {
    return this;
  }

  select(): this {
    return this;
  }

  single(): Promise<QueryResult<any>> {
    return Promise.resolve(this.supabase.execute(this.table, this.filters, this.insertBody));
  }

  then<TResult1 = QueryResult<any>, TResult2 = never>(
    onfulfilled?: ((value: QueryResult<any>) => TResult1 | PromiseLike<TResult1>) | null,
    onrejected?: ((reason: unknown) => TResult2 | PromiseLike<TResult2>) | null,
  ): Promise<TResult1 | TResult2> {
    return Promise.resolve(this.supabase.execute(this.table, this.filters, this.insertBody)).then(
      onfulfilled,
      onrejected,
    );
  }
}

function ok<T>(data: T): QueryResult<T> {
  return { data, error: null };
}

function okSession(session: unknown | null) {
  return { data: { session }, error: null };
}
