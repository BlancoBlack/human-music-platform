/**
 * Access token lives in React state (AuthContext); this getter is registered
 * on mount so `apiFetch` / `lib/api.ts` can attach `Authorization` without
 * importing React.
 */
let accessTokenGetter: (() => string | null) | null = null;
let accessTokenSetter: ((token: string | null) => void) | null = null;
const ACCESS_TOKEN_STORAGE_KEY = "hm_access_token";

export function registerAccessTokenGetter(fn: () => string | null): void {
  accessTokenGetter = fn;
}

export function unregisterAccessTokenGetter(): void {
  accessTokenGetter = null;
}

export function registerAccessTokenSetter(fn: (token: string | null) => void): void {
  accessTokenSetter = fn;
}

export function unregisterAccessTokenSetter(): void {
  accessTokenSetter = null;
}

export function updateAccessToken(token: string | null): void {
  accessTokenSetter?.(token);
}

export function getAuthHeaders(): Record<string, string> {
  const fromMemory = accessTokenGetter?.() ?? null;
  const fromStorage =
    !fromMemory && typeof window !== "undefined"
      ? window.localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)
      : null;
  const t = fromMemory || fromStorage;
  return t ? { Authorization: `Bearer ${t}` } : {};
}
