type EnvKey = Extract<keyof ImportMetaEnv, string>;

export interface BrowserConfig {
  apiUrl: string;
  supabasePublishableKey: string;
  supabaseUrl: string;
}

export class FrontendConfigurationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "FrontendConfigurationError";
  }
}

// Interactive limits and theme come from GET /api/v1/config.
export const frontendSettings = {
  queryStaleTimeMs: 30_000,
} as const;

export function readBrowserConfig(): BrowserConfig {
  const error = browserConfigError();
  if (error) {
    throw error;
  }
  return {
    apiUrl: requiredEnv("VITE_WEREWOLF_API_URL"),
    supabasePublishableKey: requiredEnv("VITE_SUPABASE_PUBLISHABLE_KEY"),
    supabaseUrl: requiredEnv("VITE_SUPABASE_URL"),
  };
}

export function browserConfigError(): FrontendConfigurationError | null {
  const missing = requiredMissingEnv([
    "VITE_WEREWOLF_API_URL",
    "VITE_SUPABASE_URL",
    "VITE_SUPABASE_PUBLISHABLE_KEY",
  ]);
  if (missing.length === 0) {
    return null;
  }
  return new FrontendConfigurationError(
    `${missing.join(" and ")} ${missing.length === 1 ? "is" : "are"} required.`,
  );
}

function requiredEnv(key: EnvKey): string {
  const value = import.meta.env[key];
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`${key} is required.`);
  }
  return value.trim();
}

function requiredMissingEnv(keys: EnvKey[]): string[] {
  return keys.filter((key) => {
    const value = import.meta.env[key];
    return typeof value !== "string" || value.trim() === "";
  });
}
