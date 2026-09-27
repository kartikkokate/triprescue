// Optional sign-in (Supabase Auth). Login is NOT enforced: a guest can use everything and
// their trips are saved anonymously. A signed-in account's trips are saved and listed per
// account - the backend verifies the access token with Supabase, never a client-sent id.
import { createClient, type Session, type SupabaseClient } from "@supabase/supabase-js";
import { api, setAccessToken } from "./api";

export type Account = { id: string; email: string; name: string };

let client: SupabaseClient | null = null;
let loading: Promise<SupabaseClient | null> | null = null;

/** Supabase client built from the backend's public config (URL + publishable key). */
export function authClient(): Promise<SupabaseClient | null> {
  if (client) return Promise.resolve(client);
  loading ??= api
    .authConfig()
    .then((cfg) => {
      if (!cfg.enabled) return null;
      client = createClient(cfg.url, cfg.key, { auth: { persistSession: true, autoRefreshToken: true } });
      return client;
    })
    .catch(() => {
      loading = null; // backend offline: allow a retry later
      return null;
    });
  return loading;
}

export function toAccount(session: Session | null): Account | null {
  const u = session?.user;
  if (!u) return null;
  const name = (u.user_metadata?.full_name as string) || u.email?.split("@")[0] || "Traveler";
  return { id: u.id, email: u.email ?? "", name };
}

/** Keeps the API token in step with the session; returns an unsubscribe function. */
export async function watchSession(onChange: (a: Account | null) => void): Promise<() => void> {
  const sb = await authClient();
  if (!sb) {
    onChange(null);
    return () => {};
  }
  const { data } = await sb.auth.getSession();
  setAccessToken(data.session?.access_token ?? null);
  onChange(toAccount(data.session));
  const sub = sb.auth.onAuthStateChange((_event, session) => {
    setAccessToken(session?.access_token ?? null);
    onChange(toAccount(session));
  });
  return () => sub.data.subscription.unsubscribe();
}

const friendly = (msg: string) =>
  /invalid login credentials/i.test(msg)
    ? "Wrong email or password."
    : /email not confirmed/i.test(msg)
      ? "Confirm your email first - check your inbox for the Supabase link."
      : /rate limit/i.test(msg)
        ? "Too many attempts right now - wait a minute and try again."
        : msg;

export async function signIn(email: string, password: string): Promise<void> {
  const sb = await authClient();
  if (!sb) throw new Error("Sign-in is unavailable (Supabase not configured). Continue as guest.");
  const { error } = await sb.auth.signInWithPassword({ email, password });
  if (error) throw new Error(friendly(error.message));
}

/** Returns "signed_in" when the project auto-confirms, "confirm_email" when a link was sent. */
export async function signUp(name: string, email: string, password: string): Promise<"signed_in" | "confirm_email"> {
  const sb = await authClient();
  if (!sb) throw new Error("Sign-up is unavailable (Supabase not configured). Continue as guest.");
  const { data, error } = await sb.auth.signUp({
    email,
    password,
    options: { data: { full_name: name }, emailRedirectTo: window.location.origin },
  });
  if (error) throw new Error(friendly(error.message));
  return data.session ? "signed_in" : "confirm_email";
}

export async function signOut(): Promise<void> {
  const sb = await authClient();
  await sb?.auth.signOut();
  setAccessToken(null);
}
