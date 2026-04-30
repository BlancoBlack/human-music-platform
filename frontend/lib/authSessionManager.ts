import { updateAccessToken } from "@/lib/authHeaders";

const ACCESS_TOKEN_STORAGE_KEY = "hm_access_token";
const REFRESH_TOKEN_STORAGE_KEY = "hm_refresh_token";
const LOGOUT_REASON_STORAGE_KEY = "hm_logout_reason";

type ForceLogoutHandler = (reason?: string) => void | Promise<void>;

let forceLogoutHandler: ForceLogoutHandler | null = null;

function canUseStorage(): boolean {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

function clearStoredTokens(): void {
  if (!canUseStorage()) return;
  window.localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY);
  window.localStorage.removeItem(REFRESH_TOKEN_STORAGE_KEY);
}

function canUseSessionStorage(): boolean {
  return typeof window !== "undefined" && typeof window.sessionStorage !== "undefined";
}

export function setLogoutReason(reason: string): void {
  if (!canUseSessionStorage()) return;
  window.sessionStorage.setItem(LOGOUT_REASON_STORAGE_KEY, reason);
}

export function consumeLogoutReason(): string | null {
  if (!canUseSessionStorage()) return null;
  const reason = window.sessionStorage.getItem(LOGOUT_REASON_STORAGE_KEY);
  if (reason) {
    window.sessionStorage.removeItem(LOGOUT_REASON_STORAGE_KEY);
  }
  return reason;
}

export function registerForceLogoutHandler(handler: ForceLogoutHandler): void {
  forceLogoutHandler = handler;
}

export function unregisterForceLogoutHandler(): void {
  forceLogoutHandler = null;
}

export async function forceLogout(reason?: string): Promise<void> {
  if (forceLogoutHandler) {
    await forceLogoutHandler(reason);
    return;
  }
  // Fallback for very early failures before AuthProvider mounts.
  updateAccessToken(null);
  clearStoredTokens();
}

