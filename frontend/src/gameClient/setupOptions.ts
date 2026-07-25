import type {
  GameScreenSource,
  GameSetupOptionsResponse,
  PublicPlayerState,
} from "./wireTypes";

const FALLBACK_SCENARIO_NAME = "霧の村";
const GENERATED_PLAYER_ID_PREFIX = "player-";
const SETUP_PREVIEW_DAY = 1;
const SETUP_PREVIEW_PHASE = "day_discussion";
const SETUP_PREVIEW_STATUS = "running";
const SETUP_PREVIEW_VERSION = 1;

export interface GeneratedSeatOption {
  id: string;
  label: string;
}

export function generatedPlayerId(index: number): string {
  return `${GENERATED_PLAYER_ID_PREFIX}${index}`;
}

export function generatedSeatOptions(playerCount: number): GeneratedSeatOption[] {
  return Array.from({ length: playerCount }, (_, index) => {
    const seatNumber = index + 1;
    return {
      id: generatedPlayerId(seatNumber),
      label: `${seatNumber}番席`,
    };
  });
}

export function playerCountFromRoles(roleCounts: Record<string, number>): number {
  return Object.values(roleCounts).reduce((sum, value) => sum + value, 0);
}

export function roleCountsForSetup(
  setupOptions: GameSetupOptionsResponse,
  setupPresetId: string,
): Record<string, number> {
  return (
    setupOptions.setup_presets.find((preset) => preset.id === setupPresetId)?.role_counts ??
    setupOptions.default_role_counts
  );
}

export function roleLabel(roleId: string, setupOptions: GameSetupOptionsResponse): string {
  return setupOptions.roles.find((role) => role.id === roleId)?.name ?? roleId;
}

export function setupPreviewScreen(setupOptions: GameSetupOptionsResponse): GameScreenSource {
  const players = setupPreviewPlayers(setupOptions);
  return {
    state: {
      game_id: "",
      status: SETUP_PREVIEW_STATUS,
      phase: SETUP_PREVIEW_PHASE,
      day: SETUP_PREVIEW_DAY,
      version: SETUP_PREVIEW_VERSION,
      seed: null,
      scenario_id: setupOptions.default_scenario_id,
      scenario_name: defaultScenarioName(setupOptions),
      narration_mode: setupOptions.default_narration_mode,
      players,
      alive_player_ids: players.map((player) => player.id),
      eliminated_player_ids: [],
      winner: null,
      summary: {},
    },
    timeline: { game_id: "", items: [], next_after: 0 },
    observation: null,
  };
}

function setupPreviewPlayers(setupOptions: GameSetupOptionsResponse): PublicPlayerState[] {
  const count = playerCountFromRoles(setupOptions.default_role_counts);
  return generatedSeatOptions(count).map((seat, index) => ({
    id: seat.id,
    name: setupOptions.characters[index]?.name ?? seat.label,
    alive: true,
    status: "alive",
  }));
}

function defaultScenarioName(setupOptions: GameSetupOptionsResponse): string {
  return (
    setupOptions.scenarios.find((scenario) => scenario.id === setupOptions.default_scenario_id)
      ?.name ??
    setupOptions.scenarios[0]?.name ??
    FALLBACK_SCENARIO_NAME
  );
}
