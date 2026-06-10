/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_SUPABASE_PUBLISHABLE_KEY?: string;
  readonly VITE_SUPABASE_URL?: string;
  readonly VITE_WEREWOLF_DEFAULT_MANUAL_PLAYER_ID?: string;
  readonly VITE_WEREWOLF_DEFAULT_SETUP_SEED?: string;
  readonly VITE_WEREWOLF_GAME_LIST_LIMIT?: string;
  readonly VITE_WEREWOLF_OPERATION_POLL_INTERVAL_MS?: string;
  readonly VITE_WEREWOLF_OPERATION_POLL_TIMEOUT_MS?: string;
  readonly VITE_WEREWOLF_QUERY_STALE_TIME_MS?: string;
  readonly VITE_WEREWOLF_TIMELINE_LIMIT?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
