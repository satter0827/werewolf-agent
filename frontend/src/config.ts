const DEFAULT_GAME_LIST_LIMIT = 20;
const DEFAULT_MANUAL_PLAYER_ID = "player-1";
const DEFAULT_OPERATION_POLL_INTERVAL_MS = 250;
const DEFAULT_OPERATION_POLL_TIMEOUT_MS = 60_000;
const DEFAULT_QUERY_STALE_TIME_MS = 30_000;
const DEFAULT_SETUP_SEED = "1";
const DEFAULT_TIMELINE_LIMIT = 100;

export interface FrontendSettings {
  defaultManualPlayerId: string;
  defaultSetupSeed: string;
  gameListLimit: number;
  operationPollIntervalMs: number;
  operationPollTimeoutMs: number;
  queryStaleTimeMs: number;
  timelineLimit: number;
}

export interface SupabaseBrowserConfig {
  publishableKey: string;
  url: string;
}

export const frontendSettings: FrontendSettings = {
  defaultManualPlayerId: optionalTextEnv(
    "VITE_WEREWOLF_DEFAULT_MANUAL_PLAYER_ID",
    DEFAULT_MANUAL_PLAYER_ID,
  ),
  defaultSetupSeed: optionalTextEnv("VITE_WEREWOLF_DEFAULT_SETUP_SEED", DEFAULT_SETUP_SEED),
  gameListLimit: positiveIntegerEnv("VITE_WEREWOLF_GAME_LIST_LIMIT", DEFAULT_GAME_LIST_LIMIT),
  operationPollIntervalMs: positiveIntegerEnv(
    "VITE_WEREWOLF_OPERATION_POLL_INTERVAL_MS",
    DEFAULT_OPERATION_POLL_INTERVAL_MS,
  ),
  operationPollTimeoutMs: positiveIntegerEnv(
    "VITE_WEREWOLF_OPERATION_POLL_TIMEOUT_MS",
    DEFAULT_OPERATION_POLL_TIMEOUT_MS,
  ),
  queryStaleTimeMs: positiveIntegerEnv(
    "VITE_WEREWOLF_QUERY_STALE_TIME_MS",
    DEFAULT_QUERY_STALE_TIME_MS,
  ),
  timelineLimit: positiveIntegerEnv("VITE_WEREWOLF_TIMELINE_LIMIT", DEFAULT_TIMELINE_LIMIT),
};

export function readSupabaseBrowserConfig(): SupabaseBrowserConfig {
  return {
    publishableKey: requiredEnv("VITE_SUPABASE_PUBLISHABLE_KEY"),
    url: requiredEnv("VITE_SUPABASE_URL"),
  };
}

function optionalTextEnv(key: keyof ImportMetaEnv, fallback: string): string {
  const value = import.meta.env[key];
  if (typeof value !== "string" || value.trim() === "") {
    return fallback;
  }
  return value.trim();
}

function positiveIntegerEnv(key: keyof ImportMetaEnv, fallback: number): number {
  const value = import.meta.env[key];
  if (typeof value !== "string" || value.trim() === "") {
    return fallback;
  }
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed <= 0) {
    throw new Error(`${key} must be a positive integer.`);
  }
  return parsed;
}

function requiredEnv(key: keyof ImportMetaEnv): string {
  const value = import.meta.env[key];
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`${key} is required.`);
  }
  return value.trim();
}
