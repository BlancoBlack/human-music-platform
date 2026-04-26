"use client";

import { usePathname } from "next/navigation";
import { AuthGuard } from "@/components/AuthGuard";
import { useAuth } from "@/context/AuthContext";
import { useOnboardingRedirect } from "@/hooks/useOnboardingRedirect";

const ONBOARDING_ROUTES = new Set([
  "/",
  "/onboarding",
  "/user-register-complete",
]);

export function OnboardingRouteGuard({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const isPublicAuthRoute = pathname === "/register" || pathname === "/login";
  const { initializing, isAuthenticated, authReady } = useAuth();
  const shouldApplyOnboardingGuard =
    isAuthenticated &&
    !isPublicAuthRoute &&
    ONBOARDING_ROUTES.has(pathname);
  const { resolving } = useOnboardingRedirect(shouldApplyOnboardingGuard);

  if (!isPublicAuthRoute && (!authReady || initializing || (isAuthenticated && resolving))) {
    return (
      <main className="mx-auto flex min-h-screen max-w-md items-center justify-center px-4 text-sm text-neutral-500 dark:text-neutral-400">
        Loading...
      </main>
    );
  }
  if (!isPublicAuthRoute && !isAuthenticated) {
    return <AuthGuard>{children}</AuthGuard>;
  }
  return <>{children}</>;
}

