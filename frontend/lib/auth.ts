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

import { API_BASE } from "@/lib/publicEnv";

const JSON_HEADERS = { "Content-Type": "application/json" } as const;

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
  const res = await fetch(`${API_BASE}/auth/register`, {
    method: "POST",
    credentials: "include",
    headers: JSON_HEADERS,
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(await readJsonError(res));
  }
  return res.json() as Promise<RegisterResponse>;
}

export async function login(email: string, password: string): Promise<TokenResponse> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    credentials: "include",
    headers: JSON_HEADERS,
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    throw new Error(await readJsonError(res));
  }
  return res.json() as Promise<TokenResponse>;
}

/**
 * Load the current user using the in-memory access token (see `AuthContext`).
 * Returns `null` if unauthenticated or session expired (no valid access token).
 */
export async function getCurrentUser(): Promise<UserMe | null> {
  const { getAuthHeaders } = await import("@/lib/authHeaders");
  const headers = getAuthHeaders();
  if (!headers.Authorization) return null;

  const res = await fetch(`${API_BASE}/auth/me`, {
    method: "GET",
    credentials: "include",
    headers: { ...headers },
  });
  if (res.status === 401 || res.status === 403) return null;
  if (!res.ok) {
    throw new Error(await readJsonError(res));
  }
  return res.json() as Promise<UserMe>;
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
  const res = await fetch(`${API_BASE}/auth/dev/impersonate`, {
    method: "POST",
    credentials: "include",
    headers: { ...JSON_HEADERS, ...getAuthHeaders() },
    body: JSON.stringify({ target_user_id: targetUserId }),
  });
  if (!res.ok) {
    throw new Error(await readJsonError(res));
  }
  return res.json() as Promise<ImpersonationTokenResponse>;
}

export async function refreshToken(): Promise<TokenResponse | null> {
  const res = await fetch(`${API_BASE}/auth/refresh`, {
    method: "POST",
    credentials: "include",
    headers: JSON_HEADERS,
    body: JSON.stringify({}),
  });
  if (res.status === 401) return null;
  if (!res.ok) {
    throw new Error(await readJsonError(res));
  }
  return res.json() as Promise<TokenResponse>;
}

/** Revokes refresh session via httpOnly cookie; does not send Authorization. */
export async function logout(): Promise<void> {
  await fetch(`${API_BASE}/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
}
