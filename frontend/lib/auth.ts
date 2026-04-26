/**
 * Browser auth against FastAPI `/auth/*`.
 *
 * - Access token: keep in React memory only (`AuthContext`); use `getAuthHeaders()` via `authHeaders` registration.
 * - Refresh token: httpOnly cookie set by the API (`hm_refresh_token`, path `/auth`). Always use `credentials: "include"`.
 *
 * DO NOT use refresh_token from JSON in browser
 * Cookie is source of truth
 *
 * @example Attach Bearer to custom fetch (same as `apiFetch` in `lib/api.ts`)
 * ```ts
 * import { getAuthHeaders } from "@/lib/authHeaders";
 * import { API_BASE } from "@/lib/publicEnv";
 * await fetch(`${API_BASE}/me`, { headers: { ...getAuthHeaders() }, credentials: "include" });
 * ```
 */

import { apiFetch } from "@/lib/api";

const JSON_HEADERS = { "Content-Type": "application/json" } as const;
const ACCESS_TOKEN_STORAGE_KEY = "hm_access_token";
const REFRESH_TOKEN_STORAGE_KEY = "hm_refresh_token";

export type TokenResponse = {
  access_token: string;
  refresh_token: string;
  token_type: string;
};

export type RegisterResponse = TokenResponse & {
  user_id: number;
  email: string;
  roles: string[];
  onboarding_completed: boolean;
  onboarding_step?: string | null;
  sub_role?: string | null;
  artist_id?: number | null;
  label_id?: number | null;
};

export type RegisterPayload = {
  email: string;
  password: string;
  username?: string;
  artist_name?: string;
  role: "user" | "artist";
  sub_role?: "artist" | "label";
};

export type ImpersonationInfo = {
  actor_id: number;
  actor_email: string | null;
};

export type UserMe = {
  id: number;
  email: string | null;
  is_active: boolean;
  is_email_verified: boolean;
  display_name: string | null;
  onboarding_completed?: boolean;
  onboarding_step?: string | null;
  sub_role?: string | null;
  roles: string[];
  impersonation?: ImpersonationInfo | null;
};

export type ImpersonationTokenResponse = {
  access_token: string;
  impersonation: boolean;
};

function canUseStorage(): boolean {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

export function setStoredTokens(tokens: {
  access_token?: string | null;
  refresh_token?: string | null;
}): void {
  if (!canUseStorage()) return;
  const access = (tokens.access_token || "").trim();
  const refresh = (tokens.refresh_token || "").trim();
  if (access) {
    window.localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, access);
  } else {
    window.localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY);
  }
  if (refresh) {
    window.localStorage.setItem(REFRESH_TOKEN_STORAGE_KEY, refresh);
  } else {
    window.localStorage.removeItem(REFRESH_TOKEN_STORAGE_KEY);
  }
}

export function getStoredAccessToken(): string | null {
  if (!canUseStorage()) return null;
  return window.localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY);
}

export function getStoredRefreshToken(): string | null {
  if (!canUseStorage()) return null;
  return window.localStorage.getItem(REFRESH_TOKEN_STORAGE_KEY);
}

export function clearStoredTokens(): void {
  if (!canUseStorage()) return;
  window.localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY);
  window.localStorage.removeItem(REFRESH_TOKEN_STORAGE_KEY);
}

async function readJsonError(res: Response): Promise<string> {
  const t = await res.text();
  try {
    const j = JSON.parse(t) as { detail?: unknown };
    if (typeof j.detail === "string") return j.detail;
  } catch {
    /* ignore */
  }
  return t || res.statusText;
}

export async function register(
  payload: RegisterPayload,
): Promise<RegisterResponse> {
  const res = await apiFetch("/auth/register", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(await readJsonError(res));
  }
  return res.json() as Promise<RegisterResponse>;
}

/**
 * Persist access/refresh tokens and load the current user with **one** `GET /auth/me`.
 * Uses an explicit `Authorization` header so it is safe immediately after minting tokens
 * (before React state propagates to the registered access-token getter).
 */
export async function applyTokens(tokens: TokenResponse): Promise<UserMe> {
  setStoredTokens(tokens);
  const access = (tokens.access_token || "").trim();
  if (!access) {
    clearStoredTokens();
    throw new Error("Missing access token");
  }
  const res = await apiFetch("/auth/me", {
    method: "GET",
    headers: { Authorization: `Bearer ${access}` },
  });
  if (res.status === 401 || res.status === 403) {
    console.warn("[auth] /auth/me unauthorized", { status: res.status });
    clearStoredTokens();
    throw new Error(await readJsonError(res));
  }
  if (!res.ok) {
    throw new Error(await readJsonError(res));
  }
  const me = (await res.json()) as UserMe;
  console.info("[auth] /auth/me success", { user_id: me.id, roles: me.roles });
  return me;
}

export async function login(email: string, password: string): Promise<TokenResponse> {
  const res = await apiFetch("/auth/login", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    console.warn("[auth] login failed", { status: res.status });
    throw new Error(await readJsonError(res));
  }
  const tokens = (await res.json()) as TokenResponse;
  console.info("[auth] login success", { has_access_token: !!tokens.access_token });
  return tokens;
}

/**
 * Load the current user using the in-memory access token (see `AuthContext`).
 * Returns `null` if unauthenticated or session expired (no valid access token).
 */
export async function getCurrentUser(): Promise<UserMe | null> {
  const { getAuthHeaders } = await import("@/lib/authHeaders");
  const headers = getAuthHeaders();
  if (!headers.Authorization) return null;

  const res = await apiFetch("/auth/me", {
    method: "GET",
    headers: { ...headers },
  });
  if (res.status === 401 || res.status === 403) {
    console.warn("[auth] /auth/me unauthorized", { status: res.status });
    return null;
  }
  if (!res.ok) {
    throw new Error(await readJsonError(res));
  }
  const me = (await res.json()) as UserMe;
  console.info("[auth] /auth/me success", { user_id: me.id, roles: me.roles });
  return me;
}

/**
 * Dev-only: mint a short-lived impersonation access JWT. Requires backend
 * ``APP_ENV=development`` (or ``dev``) and ``ENABLE_DEV_IMPERSONATION=true``.
 * Caller must already hold a normal (non-impersonation) access token.
 */
export async function impersonateUser(
  targetUserId: number,
): Promise<ImpersonationTokenResponse> {
  const { getAuthHeaders } = await import("@/lib/authHeaders");
  const res = await apiFetch("/auth/dev/impersonate", {
    method: "POST",
    headers: { ...JSON_HEADERS, ...getAuthHeaders() },
    body: JSON.stringify({ target_user_id: targetUserId }),
  });
  if (!res.ok) {
    throw new Error(await readJsonError(res));
  }
  return res.json() as Promise<ImpersonationTokenResponse>;
}

export async function refreshToken(): Promise<TokenResponse | null> {
  const res = await apiFetch("/auth/refresh", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({}),
  });
  if (res.status === 401) {
    console.warn("[auth] refresh failed", { status: 401 });
    return null;
  }
  if (!res.ok) {
    throw new Error(await readJsonError(res));
  }
  const tokens = (await res.json()) as TokenResponse;
  console.info("[auth] refresh success", { has_access_token: !!tokens.access_token });
  return tokens;
}

/** Revokes refresh session via httpOnly cookie; does not send Authorization. */
export async function logout(): Promise<void> {
  await apiFetch("/auth/logout", {
    method: "POST",
  });
}
