import { createClient, type Session, type SupabaseClient } from "@supabase/supabase-js";

import { readBrowserConfig } from "../config";

export interface AuthState {
  email: string | null;
  isAnonymous: boolean;
  isAuthenticated: boolean;
}

export class AuthClient {
  constructor(private readonly client: SupabaseClient) {}

  async accessToken(): Promise<string> {
    const current = await this.client.auth.getSession();
    if (current.error) {
      throw current.error;
    }
    if (current.data.session?.access_token) {
      return current.data.session.access_token;
    }
    const created = await this.client.auth.signInAnonymously();
    if (created.error || !created.data.session?.access_token) {
      throw created.error ?? new Error("ゲストセッションを開始できませんでした。");
    }
    return created.data.session.access_token;
  }

  async current(): Promise<AuthState> {
    const { data, error } = await this.client.auth.getSession();
    if (error) {
      throw error;
    }
    return authState(data.session);
  }

  async signIn(email: string, password: string): Promise<AuthState> {
    const { data, error } = await this.client.auth.signInWithPassword({ email, password });
    if (error) {
      throw error;
    }
    return authState(data.session);
  }

  async signOut(): Promise<AuthState> {
    const { error } = await this.client.auth.signOut();
    if (error) {
      throw error;
    }
    const { data, error: guestError } = await this.client.auth.signInAnonymously();
    if (guestError) {
      throw guestError;
    }
    return authState(data.session);
  }
}

let supabaseClient: SupabaseClient | null = null;
let defaultAuthClient: AuthClient | null = null;

function getSupabaseAuthClient(): SupabaseClient {
  if (!supabaseClient) {
    const config = readBrowserConfig();
    supabaseClient = createClient(config.supabaseUrl, config.supabasePublishableKey, {
      auth: {
        autoRefreshToken: true,
        detectSessionInUrl: false,
        persistSession: true,
      },
    });
  }
  return supabaseClient;
}

export const authClient = {
  accessToken: () => getDefaultAuthClient().accessToken(),
  current: () => getDefaultAuthClient().current(),
  signIn: (email: string, password: string) => getDefaultAuthClient().signIn(email, password),
  signOut: () => getDefaultAuthClient().signOut(),
};

function getDefaultAuthClient(): AuthClient {
  if (!defaultAuthClient) {
    defaultAuthClient = new AuthClient(getSupabaseAuthClient());
  }
  return defaultAuthClient;
}

function authState(session: Session | null): AuthState {
  return {
    email: session?.user.email ?? null,
    isAnonymous: session?.user.is_anonymous ?? true,
    isAuthenticated: Boolean(session && !session.user.is_anonymous),
  };
}
