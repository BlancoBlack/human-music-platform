"use client";

import { usePathname } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { useOnboardingRedirect } from "@/hooks/useOnboardingRedirect";

export function OnboardingRouteGuard({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const isPublicAuthRoute = pathname === "/register" || pathname === "/login";
  const { initializing, isAuthenticated } = useAuth();
  const { resolving } = useOnboardingRedirect(!isPublicAuthRoute);

  if (!isPublicAuthRoute && (initializing || (isAuthenticated && resolving))) {
    return (
      <main className="mx-auto flex min-h-screen max-w-md items-center justify-center px-4 text-sm text-neutral-500 dark:text-neutral-400">
        Loading...
      </main>
    );
  }
  return <>{children}</>;
}

