/**
 * Access token lives in React state (AuthContext); this getter is registered
 * on mount so `apiFetch` / `lib/api.ts` can attach `Authorization` without
 * importing React.
 */
let accessTokenGetter: (() => string | null) | null = null;

export function registerAccessTokenGetter(fn: () => string | null): void {
  accessTokenGetter = fn;
}

export function unregisterAccessTokenGetter(): void {
  accessTokenGetter = null;
}

export function getAuthHeaders(): Record<string, string> {
  const t = accessTokenGetter?.() ?? null;
  return t ? { Authorization: `Bearer ${t}` } : {};
}
