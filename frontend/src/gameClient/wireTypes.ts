import type { components } from "../generated/api";

type Schema<Name extends keyof components["schemas"]> = components["schemas"][Name];

export type GamePhase = Schema<"PublicGameState">["phase"];
export type GameStatus = Schema<"PublicGameState">["status"];
export type PlayerStatus = Schema<"PublicPlayerState">["status"];
export type Winner = "villagers" | "werewolves";

export type PublicPlayerState = Schema<"PublicPlayerState">;
export type PublicGameState = Omit<Schema<"PublicGameState">, "winner"> & {
  winner?: Winner | null;
};
export type PublicGameSummary = Omit<Schema<"PublicGameSummary">, "winner"> & {
  winner?: Winner | null;
};
export type GameListResponse = Omit<Schema<"GameListResponse">, "games"> & {
  games: PublicGameSummary[];
};
export type GameTimelineItem = Omit<Schema<"GameTimelineItem">, "payload"> & {
  payload: Record<string, unknown>;
};
export type GameTimelineResponse = Omit<Schema<"GameTimelineResponse">, "items"> & {
  items: GameTimelineItem[];
};

export type AvailableActionType =
  "speech" | "vote" | "seer_inspect" | "knight_guard" | "werewolf_attack" | "pass";

export interface AvailableAction {
  type: AvailableActionType;
  legal_targets?: string[];
  message_required?: boolean;
}

export interface PlayerObservationPayload {
  available_actions?: Array<AvailableAction | AvailableActionType>;
  day?: number;
  known_roles?: Record<string, string>;
  legal_targets?: Partial<Record<AvailableActionType, string[]>>;
  me?: {
    id?: string;
    name?: string;
    role?: string | null;
    status?: PlayerStatus;
  };
  phase?: GamePhase;
  role?: string | null;
  [key: string]: unknown;
}

export type PlayerObservationResponse = Omit<Schema<"PlayerObservationResponse">, "observation"> & {
  observation: PlayerObservationPayload;
};
export type RoleDefinitionView = Schema<"RoleDefinitionView">;
export type AbilityDefinitionView = Schema<"AbilityDefinitionView">;
export type AgentStrategyDefinitionView = Schema<"AgentStrategyDefinitionView">;
export type ScenarioDefinitionView = Schema<"ScenarioDefinitionView">;
export type SetupPresetDefinitionView = Schema<"SetupPresetDefinitionView">;
export type CharacterDefinitionView = Schema<"CharacterDefinitionView">;
export type LocalRulesSettings = Schema<"LocalRulesSettings">;
export type CreateGameRequest = Schema<"CreateGameRequest">;
export type GameResponse = Omit<Schema<"GameResponse">, "state"> & {
  state: PublicGameState;
};
export type PlayerActionRequest = Omit<Schema<"PlayerActionRequest">, "reason"> & {
  reason?: string;
};
export interface PlayerActionResponse {
  game_id: string;
  player_id: string;
  state: PublicGameState;
  timeline: GameTimelineItem[];
}
export type GameSetupOptionsResponse = Omit<
  Schema<"GameSetupOptionsResponse">,
  "abilities" | "agent_strategies" | "characters" | "scenarios" | "setup_presets"
> & {
  abilities: AbilityDefinitionView[];
  agent_strategies: AgentStrategyDefinitionView[];
  characters: CharacterDefinitionView[];
  scenarios: ScenarioDefinitionView[];
  setup_presets: SetupPresetDefinitionView[];
};

export interface GameScreenSource {
  state: PublicGameState;
  timeline: GameTimelineResponse;
  observation: PlayerObservationResponse | null;
}
