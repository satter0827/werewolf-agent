import type {
  CreateGameRequest,
  GameListResponse,
  GameResponse,
  GameRevealResponse,
  GameScreenSource,
  GameSetupOptionsResponse,
  PlayerActionRequest,
  PlayerActionResponse,
} from "./wireTypes";

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
  getReveal(gameId: string): Promise<GameRevealResponse | null>;
  getScreen(gameId: string | null, manualPlayerId: string): Promise<GameScreenSource>;
  getSetupOptions(): Promise<GameSetupOptionsResponse>;
  listGames(): Promise<GameListResponse>;
  submitAction(command: SubmitPlayerActionCommand): Promise<PlayerActionResponse>;
}
