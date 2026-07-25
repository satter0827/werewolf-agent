import type {
  CreateGameRequest,
  GameListResponse,
  GameResponse,
  GameScreenSource,
  GameSetupOptionsResponse,
  PlayerActionRequest,
  PlayerActionResponse,
} from "./wireTypes";
import type { components } from "../generated/api";

export type PublicRuntimeConfig = components["schemas"]["PublicRuntimeConfig"];

export interface SubmitPlayerActionCommand {
  action: PlayerActionRequest;
  gameId: string;
  playerId: string;
}

export interface AdvanceGameCommand {
  gameId: string;
}

export interface GameClient {
  advance(command: AdvanceGameCommand): Promise<GameScreenSource>;
  createGame(request: CreateGameRequest): Promise<GameResponse>;
  getRuntimeConfig(): Promise<PublicRuntimeConfig>;
  getScreen(gameId: string | null, manualPlayerId: string): Promise<GameScreenSource>;
  getSetupOptions(): Promise<GameSetupOptionsResponse>;
  listGames(): Promise<GameListResponse>;
  submitAction(command: SubmitPlayerActionCommand): Promise<PlayerActionResponse>;
}
