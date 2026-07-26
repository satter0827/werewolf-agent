import createClient, { type Client } from "openapi-fetch";

import { readBrowserConfig } from "../config";
import type { paths, components } from "../generated/api";
import type {
  GameClient,
  PublicRuntimeConfig,
  SubmitPlayerActionCommand,
} from "../gameClient/GameClient";
import type {
  CreateGameRequest,
  GameListResponse,
  GameResponse,
  GameScreenSource,
  GameSetupOptionsResponse,
  GameTimelineResponse,
  PlayerActionResponse,
  PlayerObservationResponse,
  PublicGameState,
} from "../gameClient/wireTypes";
import { authClient } from "./AuthClient";

type OperationResponse = components["schemas"]["OperationResponse"];
type ProblemDetails = components["schemas"]["ProblemDetails"];

export class ApiGameClient implements GameClient {
  private readonly api: Client<paths>;
  private readonly auth: Pick<typeof authClient, "accessToken">;
  private runtimeConfig: PublicRuntimeConfig | null = null;

  constructor(api: Client<paths>, auth: Pick<typeof authClient, "accessToken">) {
    this.api = api;
    this.auth = auth;
    this.api.use({
      onRequest: async ({ request }) => {
        const token = await this.accessToken();
        request.headers.set("Authorization", `Bearer ${token}`);
        return request;
      },
    });
  }

  async getRuntimeConfig(): Promise<PublicRuntimeConfig> {
    if (this.runtimeConfig) {
      return this.runtimeConfig;
    }
    const { data, error } = await this.api.GET("/api/v1/config");
    this.runtimeConfig = requireData(data, error);
    return this.runtimeConfig;
  }

  async getSetupOptions(): Promise<GameSetupOptionsResponse> {
    const config = await this.getRuntimeConfig();
    return normalizeSetup(config.setup);
  }

  async createGame(request: CreateGameRequest): Promise<GameResponse> {
    const response = await this.api.POST("/api/v1/games", {
      body: request,
      params: { header: { "Idempotency-Key": createIdempotencyKey() } },
    });
    const operation = requireData(response.data, response.error);
    return this.operationResult<GameResponse>(await this.waitForOperation(operation));
  }

  async listGames(): Promise<GameListResponse> {
    const config = await this.getRuntimeConfig();
    const { data, error } = await this.api.GET("/api/v1/games", {
      params: {
        query: {
          limit: config.limits.game_list_page_size,
          offset: 0,
        },
      },
    });
    return requireData(data, error) as GameListResponse;
  }

  async getScreen(gameId: string | null, manualPlayerId: string): Promise<GameScreenSource> {
    if (!gameId) {
      throw new Error("ゲームが選択されていません。");
    }
    const config = await this.getRuntimeConfig();
    const [state, timeline, observation] = await Promise.all([
      this.getGameState(gameId),
      this.getTimeline(gameId, config.limits.timeline_page_size),
      manualPlayerId ? this.getObservation(gameId, manualPlayerId) : Promise.resolve(null),
    ]);
    return { state, timeline, observation };
  }

  async advance({ gameId }: { gameId: string }): Promise<GameScreenSource> {
    const state = await this.getGameState(gameId);
    const response = await this.api.POST("/api/v1/games/{game_id}/advance", {
      params: {
        path: { game_id: gameId },
        header: { "Idempotency-Key": createIdempotencyKey() },
      },
      body: { expected_version: state.version },
    });
    const operation = requireData(response.data, response.error);
    await this.waitForOperation(operation);
    return this.getScreen(gameId, "");
  }

  async submitAction(command: SubmitPlayerActionCommand): Promise<PlayerActionResponse> {
    const state = await this.getGameState(command.gameId);
    const response = await this.api.POST("/api/v1/games/{game_id}/actions", {
      params: {
        path: { game_id: command.gameId },
        header: { "Idempotency-Key": createIdempotencyKey() },
      },
      body: {
        action: {
          ...command.action,
          reason: command.action.reason ?? "",
        },
        expected_version: state.version,
        player_id: command.playerId,
      },
    });
    const operation = requireData(response.data, response.error);
    return this.operationResult<PlayerActionResponse>(await this.waitForOperation(operation));
  }

  private async getGameState(gameId: string): Promise<PublicGameState> {
    const { data, error } = await this.api.GET("/api/v1/games/{game_id}", {
      params: { path: { game_id: gameId } },
    });
    return (requireData(data, error) as GameResponse).state;
  }

  private async getTimeline(gameId: string, limit: number): Promise<GameTimelineResponse> {
    const { data, error } = await this.api.GET("/api/v1/games/{game_id}/timeline", {
      params: {
        path: { game_id: gameId },
        query: { after: 0, limit },
      },
    });
    const timeline = requireData(data, error) as GameTimelineResponse;
    return {
      ...timeline,
      items: timeline.items.map((item) => ({ ...item, payload: item.payload ?? {} })),
    };
  }

  private async getObservation(
    gameId: string,
    playerId: string,
  ): Promise<PlayerObservationResponse | null> {
    const result = await this.api.GET("/api/v1/games/{game_id}/observation/{player_id}", {
      params: { path: { game_id: gameId, player_id: playerId } },
    });
    if (result.response.status === 403 || result.response.status === 404) {
      return null;
    }
    return requireData(result.data, result.error) as PlayerObservationResponse;
  }

  private async waitForOperation(operation: OperationResponse): Promise<OperationResponse> {
    const config = await this.getRuntimeConfig();
    const pollInterval = config.ui.operation_poll_interval_ms;
    const timeout = config.ui.operation_poll_timeout_ms;
    const deadline = Date.now() + timeout;
    let current = operation;
    while (current.status === "queued" || current.status === "running") {
      if (Date.now() >= deadline) {
        throw new Error("操作が時間内に完了しませんでした。");
      }
      await delay(pollInterval);
      try {
        const result = await this.api.GET("/api/v1/operations/{operation_id}", {
          params: { path: { operation_id: current.operation_id } },
        });
        if (result.data !== undefined) {
          current = result.data;
        } else if (!isRetryableProblem(result.error)) {
          throwProblem(result.error);
        }
      } catch (error) {
        if (!(error instanceof TypeError)) throw error;
      }
    }
    if (current.status === "failed") {
      throw new Error(current.error?.detail ?? "操作に失敗しました。");
    }
    return current;
  }

  private operationResult<T>(operation: OperationResponse): T {
    if (!operation.result) {
      throw new Error("完了した操作に結果がありません。");
    }
    return operation.result as T;
  }

  private async accessToken(): Promise<string> {
    return this.auth.accessToken();
  }
}

let defaultClient: ApiGameClient | null = null;

export const gameClient: GameClient = {
  advance: (command) => getDefaultClient().advance(command),
  createGame: (request) => getDefaultClient().createGame(request),
  getRuntimeConfig: () => getDefaultClient().getRuntimeConfig(),
  getScreen: (gameId, manualPlayerId) => getDefaultClient().getScreen(gameId, manualPlayerId),
  getSetupOptions: () => getDefaultClient().getSetupOptions(),
  listGames: () => getDefaultClient().listGames(),
  submitAction: (command) => getDefaultClient().submitAction(command),
};

function getDefaultClient(): ApiGameClient {
  if (!defaultClient) {
    const config = readBrowserConfig();
    defaultClient = new ApiGameClient(createClient<paths>({ baseUrl: config.apiUrl }), authClient);
  }
  return defaultClient;
}

function requireData<T>(data: T | undefined, error: unknown): T {
  if (data !== undefined) {
    return data;
  }
  throwProblem(error);
}

function throwProblem(error: unknown): never {
  const problem = error as ProblemDetails | undefined;
  throw new Error(problem?.detail ?? "API要求に失敗しました。");
}

function isRetryableProblem(error: unknown): boolean {
  return Boolean((error as ProblemDetails | undefined)?.retryable);
}

function normalizeSetup(
  value: components["schemas"]["GameSetupOptionsResponse"],
): GameSetupOptionsResponse {
  return {
    ...value,
    abilities: value.abilities ?? [],
    characters: value.characters ?? [],
    scenarios: value.scenarios ?? [],
    setup_presets: value.setup_presets ?? [],
  };
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

type IdempotencyCrypto = Pick<Crypto, "getRandomValues"> & Partial<Pick<Crypto, "randomUUID">>;

export function createIdempotencyKey(source: IdempotencyCrypto = globalThis.crypto): string {
  if (typeof source.randomUUID === "function") {
    return source.randomUUID();
  }
  const bytes = source.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6]! & 0x0f) | 0x40;
  bytes[8] = (bytes[8]! & 0x3f) | 0x80;
  const hex = [...bytes].map((value) => value.toString(16).padStart(2, "0"));
  return [
    hex.slice(0, 4).join(""),
    hex.slice(4, 6).join(""),
    hex.slice(6, 8).join(""),
    hex.slice(8, 10).join(""),
    hex.slice(10).join(""),
  ].join("-");
}
