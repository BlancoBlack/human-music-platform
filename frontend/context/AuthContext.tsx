"use client";

/**
 * Auth session cache
 *
 * DO NOT use refresh_token from JSON in browser
 * Cookie is source of truth
 *
 * `/auth/me` runs from `lib/auth.ts` (`applyTokens`, `getCurrentUser`) and this module:
 * - after login / register (`applyTokens` → single `/auth/me`)
 * - after cookie refresh (`refreshSession` → `auth.applyTokens`)
 *
 * Components should read `user` from `useAuth()` — do not call `getCurrentUser()` directly.
 * Use `refreshUser()` when profile/roles may have changed server-side.
 *
 * In React Strict Mode (dev), the bootstrap effect may still run twice; a module-level
 * `refreshPromise` coalesces concurrent `refreshSession()` calls so only one
 * `auth.refreshToken()` runs at a time (per tab). Production uses a single mount.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import * as auth from "@/lib/auth";
import type { UserMe } from "@/lib/auth";
import {
  registerAccessTokenGetter,
  unregisterAccessTokenGetter,
} from "@/lib/authHeaders";

/** Single-flight refresh: one in-flight `refreshToken()` per tab (Strict Mode / parallel callers). */
let refreshPromise: Promise<boolean> | null = null;

type AuthContextValue = {
  user: UserMe | null;
  accessToken: string | null;
  initializing: boolean;
  authReady: boolean;
  isAuthenticated: boolean;
  /** True when access JWT is a dev impersonation token (`/auth/me` includes `impersonation`). */
  isImpersonating: boolean;
  login: (email: string, password: string) => Promise<UserMe>;
  register: (payload: auth.RegisterPayload) => Promise<UserMe>;
  logout: () => Promise<void>;
  refreshSession: () => Promise<boolean>;
  /** One `/auth/me` fetch; use after profile-changing server actions. */
  refreshUser: () => Promise<UserMe | null>;
  /** Dev-only: act as another user (requires backend flags). */
  impersonateUser: (targetUserId: number) => Promise<void>;
  /** Exit impersonation by refreshing the real session from the httpOnly cookie. */
  exitImpersonation: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserMe | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [initializing, setInitializing] = useState(true);
  const tokenRef = useRef<string | null>(null);
  tokenRef.current = accessToken;

  useEffect(() => {
    registerAccessTokenGetter(() => tokenRef.current);
    return () => unregisterAccessTokenGetter();
  }, []);

  const commitAccessToken = useCallback((token: string | null) => {
    tokenRef.current = token;
    setAccessToken(token);
  }, []);

  /** Single place that calls `GET /auth/me` (requires token already on `tokenRef`). */
  const syncUserFromMe = useCallback(async (): Promise<UserMe | null> => {
    const me = await auth.getCurrentUser();
    setUser(me);
    return me;
  }, []);

  const applyTokensFromResponse = useCallback(
    async (tokens: auth.TokenResponse): Promise<UserMe> => {
      commitAccessToken(tokens.access_token);
      const me = await auth.applyTokens(tokens);
      setUser(me);
      return me;
    },
    [commitAccessToken],
  );

  const refreshSession = useCallback(async (): Promise<boolean> => {
    if (refreshPromise !== null) {
      return refreshPromise;
    }
    refreshPromise = (async (): Promise<boolean> => {
      try {
        const tokens = await auth.refreshToken();
        if (!tokens?.access_token) {
          commitAccessToken(null);
          auth.clearStoredTokens();
          setUser(null);
          return false;
        }
        commitAccessToken(tokens.access_token);
        const me = await auth.applyTokens(tokens);
        setUser(me);
        return me != null;
      } catch (error) {
        console.warn("Refresh failed", error);
        setUser(null);
        commitAccessToken(null);
        auth.clearStoredTokens();
        return false;
      } finally {
        refreshPromise = null;
      }
    })();
    return refreshPromise;
  }, [commitAccessToken]);

  const refreshUser = useCallback(async () => {
    if (!tokenRef.current) {
      setUser(null);
      return null;
    }
    return syncUserFromMe();
  }, [syncUserFromMe]);

  const impersonateUserFn = useCallback(
    async (targetUserId: number) => {
      const res = await auth.impersonateUser(targetUserId);
      commitAccessToken(res.access_token);
      await syncUserFromMe();
    },
    [commitAccessToken, syncUserFromMe],
  );

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const storedAccess = auth.getStoredAccessToken();
        const storedRefresh = auth.getStoredRefreshToken();
        console.info("[auth] bootstrap", {
          has_stored_access_token: !!storedAccess,
          has_stored_refresh_token: !!storedRefresh,
        });
        if (storedAccess) {
          commitAccessToken(storedAccess);
          const me = await syncUserFromMe();
          if (!cancelled && me) {
            setUser(me);
          }
          if (!me && storedRefresh) {
            const ok = await refreshSession();
            if (!cancelled && !ok) {
              setUser(null);
              commitAccessToken(null);
            }
          } else if (!me && !storedRefresh) {
            auth.clearStoredTokens();
            setUser(null);
            commitAccessToken(null);
          }
        } else if (storedRefresh) {
          const ok = await refreshSession();
          if (!cancelled && !ok) {
            setUser(null);
            commitAccessToken(null);
          }
        } else {
          setUser(null);
          commitAccessToken(null);
        }
      } catch {
        if (!cancelled) {
          setUser(null);
          commitAccessToken(null);
          auth.clearStoredTokens();
        }
      } finally {
        if (!cancelled) setInitializing(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshSession, commitAccessToken, syncUserFromMe]);

  const login = useCallback(
    async (email: string, password: string) => {
      const tokens = await auth.login(email, password);
      return applyTokensFromResponse(tokens);
    },
    [applyTokensFromResponse],
  );

  const register = useCallback(
    async (payload: auth.RegisterPayload) => {
      const response = await auth.register(payload);
      const tokens = {
        access_token: response.access_token,
        refresh_token: response.refresh_token,
        token_type: response.token_type,
      };
      return applyTokensFromResponse(tokens);
    },
    [applyTokensFromResponse],
  );

  const logout = useCallback(async () => {
    try {
      await auth.logout();
    } catch (e) {
      console.warn("Logout failed", e);
    }
    commitAccessToken(null);
    auth.clearStoredTokens();
    setUser(null);
  }, [commitAccessToken]);

  const exitImpersonation = useCallback(async () => {
    const ok = await refreshSession();
    if (!ok) {
      await logout();
    }
  }, [refreshSession, logout]);

  const isImpersonating = Boolean(user?.impersonation);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      accessToken,
      initializing,
      authReady: !initializing,
      isAuthenticated: user != null && !!accessToken,
      isImpersonating,
      login,
      register,
      logout,
      refreshSession,
      refreshUser,
      impersonateUser: impersonateUserFn,
      exitImpersonation,
    }),
    [
      user,
      accessToken,
      initializing,
      isImpersonating,
      login,
      register,
      logout,
      refreshSession,
      refreshUser,
      impersonateUserFn,
      exitImpersonation,
    ],
  );

  return (
    <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}
