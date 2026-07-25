import { useState, type FormEvent } from "react";

import type { AuthState } from "../../../data/AuthClient";

interface AuthPanelProps {
  auth: AuthState;
  isPending: boolean;
  onSignIn: (email: string, password: string) => void;
  onSignOut: () => void;
}

export function AuthPanel({ auth, isPending, onSignIn, onSignOut }: AuthPanelProps) {
  const [expanded, setExpanded] = useState(false);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    onSignIn(String(form.get("email") ?? ""), String(form.get("password") ?? ""));
  }

  if (auth.isAuthenticated) {
    return (
      <div className="wa-auth-panel" aria-label="アカウント">
        <span className="wa-auth-state">ログイン中</span>
        <span className="wa-auth-email">{auth.email}</span>
        <button type="button" disabled={isPending} onClick={onSignOut}>
          ログアウト
        </button>
      </div>
    );
  }

  return (
    <div className="wa-auth-panel" aria-label="アカウント">
      <span className="wa-auth-state">ゲストで利用中</span>
      {expanded ? (
        <form className="wa-auth-form" onSubmit={submit}>
          <label>
            メールアドレス
            <input name="email" type="email" autoComplete="email" required maxLength={254} />
          </label>
          <label>
            パスワード
            <input
              name="password"
              type="password"
              autoComplete="current-password"
              required
              minLength={8}
              maxLength={128}
            />
          </label>
          <div className="wa-auth-actions">
            <button type="submit" disabled={isPending}>ログイン</button>
            <button type="button" disabled={isPending} onClick={() => setExpanded(false)}>
              閉じる
            </button>
          </div>
        </form>
      ) : (
        <button type="button" onClick={() => setExpanded(true)}>ログイン</button>
      )}
    </div>
  );
}
