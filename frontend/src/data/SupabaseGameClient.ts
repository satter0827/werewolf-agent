import { createClient } from "@supabase/supabase-js";

import { frontendSettings, readSupabaseBrowserConfig } from "../config";
import type { GameClient, SubmitPlayerActionCommand } from "../gameClient/GameClient";
import type {
  CreateGameRequest,
  GameListResponse,
  GameResponse,
  GameRevealResponse,
  GameScreenSource,
  GameSetupOptionsResponse,
  GameTimelineItem,
  GameTimelineResponse,
  PlayerActionResponse,
  PlayerObservationResponse,
  PublicGameState,
  PublicGameSummary,
} from "../gameClient/wireTypes";

type SupabaseErrorLike = { code?: string; details?: string; hint?: string; message: string };
type SupabaseQueryResult<T> = { data: T | null; error: SupabaseErrorLike | null };
type SupabaseSessionResult = {
  data: { session: unknown | null };
  error: SupabaseErrorLike | null;
};
type SupabaseClientPort = {
  auth: {
    getSession(): Promise<SupabaseSessionResult>;
    signInAnonymously(): Promise<SupabaseSessionResult>;
  };
  from(table: string): any;
};

interface OperationRow {
  error_payload?: { detail?: string; message?: string } | null;
  request_id: string;
  result_payload?: unknown;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
}

interface SupabaseGameClientOptions {
  pollIntervalMs?: number;
  pollTimeoutMs?: number;
}

const NO_PLAYER_ID = "";
const POSTGREST_NO_ROWS = "PGRST116";
const TERMINAL_OPERATION_STATUSES = new Set<OperationRow["status"]>([
  "completed",
  "failed",
  "cancelled",
]);

const OPERATIONS = {
  advanceGame: "advance_game",
  createGame: "create_game",
  submitAction: "submit_action",
} as const;

const TABLES = {
  definitionItems: "definition_items",
  gameOperationRequests: "game_operation_requests",
  gamePlayerObservations: "game_player_observations",
  gamePublicTurns: "game_public_turns",
  gameReveals: "game_reveals",
  gameSummaries: "game_summaries",
  games: "games",
} as const;

export class SupabaseGameClient implements GameClient {
  private readonly client: SupabaseClientPort;
  private readonly pollIntervalMs: number;
  private readonly pollTimeoutMs: number;
  private sessionReady = false;
  private sessionRequest: Promise<void> | null = null;

  constructor(client: SupabaseClientPort, options: SupabaseGameClientOptions = {}) {
    this.client = client;
    this.pollIntervalMs = options.pollIntervalMs ?? frontendSettings.operationPollIntervalMs;
    this.pollTimeoutMs = options.pollTimeoutMs ?? frontendSettings.operationPollTimeoutMs;
  }

  async advance({ gameId }: { gameId: string }): Promise<GameScreenSource> {
    await this.enqueueOperation(OPERATIONS.advanceGame, {}, { gameId });
    return this.getScreen(gameId, NO_PLAYER_ID);
  }

  async createGame(request: CreateGameRequest): Promise<GameResponse> {
    const row = await this.enqueueOperation(OPERATIONS.createGame, request);
    return requireResultPayload(row);
  }

  async getReveal(gameId: string): Promise<GameRevealResponse | null> {
    await this.ensureSession();
    const row = await optionalSingle<{ reveal_payload: GameRevealResponse }>(
      this.client
        .from(TABLES.gameReveals)
        .select("reveal_payload")
        .eq("game_id", gameId)
        .limit(1)
        .maybeSingle(),
      "read game reveal",
    );
    return row?.reveal_payload ?? null;
  }

  async getScreen(gameId: string | null, manualPlayerId: string): Promise<GameScreenSource> {
    if (!gameId) {
      throw new Error("Game is not selected.");
    }
    await this.ensureSession();
    const [state, timeline, observation] = await Promise.all([
      this.getGameState(gameId),
      this.getTimeline(gameId),
      this.getObservation(gameId, manualPlayerId),
    ]);
    return { state, timeline, observation, reveal: null };
  }

  async getSetupOptions(): Promise<GameSetupOptionsResponse> {
    await this.ensureSession();
    const row = await requiredSingle<{ payload: GameSetupOptionsResponse }>(
      this.client
        .from(TABLES.definitionItems)
        .select("payload")
        .eq("scope", "system")
        .eq("kind", "setup_options")
        .eq("item_key", "default")
        .eq("active", true)
        .limit(1)
        .single(),
      "read setup options",
    );
    return row.payload;
  }

  async listGames(): Promise<GameListResponse> {
    await this.ensureSession();
    const games = await requiredRows<PublicGameSummary>(
      this.client
        .from(TABLES.gameSummaries)
        .select("*")
        .order("updated_at", { ascending: false })
        .limit(frontendSettings.gameListLimit),
      "list games",
    );
    return {
      games,
      next_offset: games.length === frontendSettings.gameListLimit ? games.length : null,
    };
  }

  async submitAction(command: SubmitPlayerActionCommand): Promise<PlayerActionResponse> {
    const row = await this.enqueueOperation(OPERATIONS.submitAction, command.action, {
      gameId: command.gameId,
      playerId: command.playerId,
    });
    return requireResultPayload(row);
  }

  async ensureSession(): Promise<void> {
    if (this.sessionReady) {
      return;
    }
    if (this.sessionRequest === null) {
      this.sessionRequest = this.resolveSession().finally(() => {
        this.sessionRequest = null;
      });
    }
    await this.sessionRequest;
  }

  private async resolveSession(): Promise<void> {
    const current = await this.client.auth.getSession();
    throwIfError(current.error, "read Supabase session");
    if (current.data.session) {
      this.sessionReady = true;
      return;
    }
    const created = await this.client.auth.signInAnonymously();
    throwIfError(created.error, "create anonymous Supabase session");
    if (!created.data.session) {
      throw new Error("create anonymous Supabase session: session is missing.");
    }
    this.sessionReady = true;
  }

  private async getGameState(gameId: string): Promise<PublicGameState> {
    const row = await requiredSingle<{ public_state: PublicGameState }>(
      this.client
        .from(TABLES.games)
        .select("public_state")
        .eq("game_id", gameId)
        .limit(1)
        .single(),
      "read game",
    );
    return row.public_state;
  }

  private async getTimeline(gameId: string): Promise<GameTimelineResponse> {
    const rows = await requiredRows<Record<string, unknown>>(
      this.client
        .from(TABLES.gamePublicTurns)
        .select("*")
        .eq("game_id", gameId)
        .order("sequence", { ascending: true })
        .limit(frontendSettings.timelineLimit),
      "read public timeline",
    );
    const items = rows.map((row) => timelineItem(row));
    return {
      game_id: gameId,
      items,
      next_after: items.length > 0 ? items[items.length - 1].sequence : 0,
    };
  }

  private async getObservation(
    gameId: string,
    manualPlayerId: string,
  ): Promise<PlayerObservationResponse | null> {
    if (!manualPlayerId) {
      return null;
    }
    return optionalSingle<PlayerObservationResponse>(
      this.client
        .from(TABLES.gamePlayerObservations)
        .select("game_id,player_id,observation")
        .eq("game_id", gameId)
        .eq("player_id", manualPlayerId)
        .limit(1)
        .maybeSingle(),
      "read player observation",
    );
  }

  private async enqueueOperation(
    operationType: string,
    payload: object,
    context: { gameId?: string; playerId?: string } = {},
  ): Promise<OperationRow> {
    await this.ensureSession();
    const body: Record<string, unknown> = {
      operation_type: operationType,
      request_payload: payload,
    };
    if (context.gameId) {
      body.game_id = context.gameId;
    }
    if (context.playerId) {
      body.player_id = context.playerId;
    }
    const row = await requiredSingle<OperationRow>(
      this.client
        .from(TABLES.gameOperationRequests)
        .insert(body)
        .select("*")
        .single(),
      `enqueue ${operationType}`,
    );
    return this.waitForOperation(row.request_id);
  }

  private async waitForOperation(requestId: string): Promise<OperationRow> {
    const deadline = Date.now() + this.pollTimeoutMs;
    while (Date.now() <= deadline) {
      const row = await requiredSingle<OperationRow>(
        this.client
          .from(TABLES.gameOperationRequests)
          .select("*")
          .eq("request_id", requestId)
          .limit(1)
          .single(),
        "poll operation",
      );
      if (TERMINAL_OPERATION_STATUSES.has(row.status)) {
        if (row.status === "completed") {
          return row;
        }
        throw new Error(queueError(row));
      }
      await delay(this.pollIntervalMs);
    }
    throw new Error("Supabase operation timed out.");
  }
}

let defaultClient: SupabaseGameClient | null = null;

export const gameClient: GameClient = {
  advance: (command) => getDefaultClient().advance(command),
  createGame: (request) => getDefaultClient().createGame(request),
  getReveal: (gameId) => getDefaultClient().getReveal(gameId),
  getScreen: (gameId, manualPlayerId) => getDefaultClient().getScreen(gameId, manualPlayerId),
  getSetupOptions: () => getDefaultClient().getSetupOptions(),
  listGames: () => getDefaultClient().listGames(),
  submitAction: (command) => getDefaultClient().submitAction(command),
};

function getDefaultClient(): SupabaseGameClient {
  defaultClient ??= new SupabaseGameClient(createBrowserSupabaseClient());
  return defaultClient;
}

function createBrowserSupabaseClient(): SupabaseClientPort {
  const config = readSupabaseBrowserConfig();
  return createClient(config.url, config.publishableKey, {
    auth: {
      autoRefreshToken: true,
      detectSessionInUrl: false,
      persistSession: true,
    },
  }) as SupabaseClientPort;
}

async function requiredSingle<T>(query: Promise<SupabaseQueryResult<T>>, context: string): Promise<T> {
  const { data, error } = await query;
  throwIfError(error, context);
  if (data === null) {
    throw new Error(`${context}: no row returned.`);
  }
  return data;
}

async function optionalSingle<T>(
  query: Promise<SupabaseQueryResult<T>>,
  context: string,
): Promise<T | null> {
  const { data, error } = await query;
  if (error?.code === POSTGREST_NO_ROWS) {
    return null;
  }
  throwIfError(error, context);
  return data;
}

async function requiredRows<T>(
  query: Promise<SupabaseQueryResult<T[]>>,
  context: string,
): Promise<T[]> {
  const { data, error } = await query;
  throwIfError(error, context);
  return data ?? [];
}

function throwIfError(error: SupabaseErrorLike | null, context: string): void {
  if (error) {
    throw new Error(`${context}: ${error.message}`);
  }
}

function requireResultPayload<T>(row: OperationRow): T {
  if (typeof row.result_payload !== "object" || row.result_payload === null) {
    throw new Error("Supabase operation completed without result payload.");
  }
  return row.result_payload as T;
}

function queueError(row: OperationRow): string {
  return row.error_payload?.detail ?? row.error_payload?.message ?? "Supabase operation failed.";
}

function timelineItem(row: Record<string, unknown>): GameTimelineItem {
  return {
    sequence: Number(row.sequence),
    event_sequence: Number(row.event_sequence),
    version: Number(row.version),
    phase: (row.phase ?? null) as GameTimelineItem["phase"],
    day: row.day === null || row.day === undefined ? null : Number(row.day),
    actor_id: (row.actor_id ?? null) as string | null,
    event_type: String(row.event_type),
    narration: (row.narration ?? null) as string | null,
    payload:
      typeof row.payload === "object" && row.payload !== null
        ? (row.payload as Record<string, unknown>)
        : {},
    occurred_at: String(row.occurred_at),
  };
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}
