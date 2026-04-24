"use client";

import { useEffect, useMemo } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { resolveOnboardingRoute } from "@/lib/onboarding";

export function useOnboardingRedirect(enabled = true): {
  targetRoute: "/onboarding" | "/player" | null;
  resolving: boolean;
} {
  const router = useRouter();
  const pathname = usePathname();
  const { user, isAuthenticated } = useAuth();

  const targetRoute = useMemo(
    () => (enabled && isAuthenticated ? resolveOnboardingRoute(user) : null),
    [enabled, isAuthenticated, user],
  );

  useEffect(() => {
    if (!enabled || !isAuthenticated || !targetRoute) return;
    if (pathname !== targetRoute) {
      router.replace(targetRoute);
    }
  }, [enabled, isAuthenticated, pathname, router, targetRoute]);

  const resolving = Boolean(
    enabled && isAuthenticated && targetRoute && pathname !== targetRoute,
  );
  return { targetRoute, resolving };
}

