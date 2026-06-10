export type GamePhase = "night" | "day_discussion" | "voting" | "finished";
export type GameStatus = "running" | "completed";
export type PlayerStatus = "alive" | "dead";
export type Winner = "villagers" | "werewolves";

export interface PublicPlayerState {
  id: string;
  name: string;
  alive: boolean;
  status: PlayerStatus;
  eliminated_day?: number | null;
  killed_night?: number | null;
}

export interface PublicGameState {
  game_id: string;
  status: GameStatus;
  phase: GamePhase;
  day: number;
  version: number;
  seed: number | null;
  scenario_id?: string | null;
  scenario_name?: string | null;
  narration_mode: string;
  players: PublicPlayerState[];
  alive_player_ids: string[];
  eliminated_player_ids: string[];
  winner?: Winner | null;
  summary: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface PublicGameSummary {
  game_id: string;
  status: GameStatus;
  phase: GamePhase;
  day: number;
  version: number;
  seed: number | null;
  player_count: number;
  alive_count: number;
  winner?: Winner | null;
  step_count: number;
  turn_count: number;
  created_at: string;
  updated_at: string;
  completed_at?: string | null;
}

export interface GameListResponse {
  games: PublicGameSummary[];
  next_offset: number | null;
}

export interface GameTimelineItem {
  sequence: number;
  event_sequence: number;
  version: number;
  phase?: GamePhase | null;
  day?: number | null;
  actor_id?: string | null;
  event_type: string;
  narration?: string | null;
  payload: Record<string, unknown>;
  occurred_at: string;
}

export interface GameTimelineResponse {
  game_id: string;
  items: GameTimelineItem[];
  next_after: number;
}

export interface AvailableAction {
  type: "speech" | "vote" | "seer_inspect" | "knight_guard" | "werewolf_attack" | "pass";
  legal_targets?: string[];
  message_required?: boolean;
}

export interface PlayerObservationPayload {
  available_actions?: Array<AvailableAction | PlayerActionRequest["type"]>;
  day?: number;
  known_roles?: Record<string, string>;
  legal_targets?: Partial<Record<PlayerActionRequest["type"], string[]>>;
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

export interface PlayerObservationResponse {
  game_id: string;
  player_id: string;
  observation: PlayerObservationPayload;
}

export interface GameRevealPlayer {
  id: string;
  name: string;
  role: string;
  faction: string;
  alive: boolean;
  status: PlayerStatus;
}

export interface GameRevealAction {
  player_id: string;
  type: string;
  target_id?: string | null;
  message?: string | null;
}

export interface GameRevealVote {
  day: number;
  votes: Record<string, string>;
  counts: Record<string, number>;
  tied_player_ids: string[];
  missing_voter_ids: string[];
  eliminated_player_id?: string | null;
  tie_break_policy: string;
}

export interface GameRevealNight {
  day: number;
  attacked_player_id?: string | null;
  protected_player_id?: string | null;
  killed_player_id?: string | null;
}

export interface GameRevealResponse {
  game_id: string;
  status: GameStatus;
  phase: GamePhase;
  day: number;
  version: number;
  seed: number | null;
  scenario_id?: string | null;
  scenario_name?: string | null;
  narration_mode: string;
  role_counts: Record<string, number>;
  rules: LocalRulesSettings;
  players: GameRevealPlayer[];
  alive_player_ids: string[];
  eliminated_player_ids: string[];
  winner?: Winner | null;
  pending_votes: GameRevealAction[];
  pending_night_actions: GameRevealAction[];
  votes: GameRevealVote[];
  nights: GameRevealNight[];
}

export interface RoleDefinitionView {
  id: string;
  name: string;
  faction: string;
  abilities: string[];
  description: string;
  difficulty: number;
}

export interface AbilityDefinitionView {
  id: string;
  name: string;
  description: string;
  target_policy: string;
  difficulty: number;
}

export interface AgentStrategyDefinitionView {
  id: string;
  name: string;
  description: string;
}

export interface ScenarioDefinitionView {
  id: string;
  name: string;
  summary: string;
  recommended_setup_preset?: string | null;
}

export interface SetupPresetDefinitionView {
  id: string;
  name: string;
  scenario_id: string;
  role_counts: Record<string, number>;
}

export interface CharacterDefinitionView {
  id: string;
  name: string;
  age: number;
  gender: string;
  personality: string;
  speaking_style: string;
  reasoning_style: string;
  risk_tolerance: string;
}

export interface LocalRulesSettings {
  day_speech_limit_per_player: number;
  allow_self_vote: boolean;
  allow_vote_revision: boolean;
  allow_night_action_revision: boolean;
  enable_first_night_attack: boolean;
  enable_no_elimination_on_tie: boolean;
  enable_random_elimination_on_tie: boolean;
  allow_knight_self_guard: boolean;
  allow_knight_repeat_guard: boolean;
  allow_seer_self_inspect: boolean;
  allow_werewolf_friendly_fire: boolean;
  reveal_role_on_death: boolean;
}

export interface CreateGameRequest {
  seed: number | null;
  scenario_id?: string | null;
  setup_preset_id?: string | null;
  agent_strategy_id?: string | null;
  narration_mode?: string | null;
  role_counts: Record<string, number>;
  manual_player_id?: string | null;
  rules?: LocalRulesSettings | null;
  character_assignments?: Record<string, string>;
  custom_characters?: unknown[];
  custom_roles?: unknown[];
}

export interface GameResponse {
  game_id: string;
  state: PublicGameState;
}

export interface PlayerActionRequest {
  type: "speech" | "vote" | "seer_inspect" | "knight_guard" | "werewolf_attack" | "pass";
  message?: string | null;
  reason?: string;
  target_id?: string | null;
}

export interface PlayerActionResponse {
  game_id: string;
  player_id: string;
  state: PublicGameState;
  timeline: GameTimelineItem[];
}

export interface GameSetupOptionsResponse {
  player_count: Record<string, number>;
  roles: RoleDefinitionView[];
  default_role_counts: Record<string, number>;
  default_rules: LocalRulesSettings;
  default_scenario_id?: string | null;
  default_setup_preset_id?: string | null;
  default_narration_mode: string;
  default_agent_strategy_id: string;
  abilities: AbilityDefinitionView[];
  scenarios: ScenarioDefinitionView[];
  setup_presets: SetupPresetDefinitionView[];
  characters: CharacterDefinitionView[];
  agent_strategies: AgentStrategyDefinitionView[];
}

export interface GameScreenSource {
  state: PublicGameState;
  timeline: GameTimelineResponse;
  observation: PlayerObservationResponse | null;
  reveal: GameRevealResponse | null;
}
