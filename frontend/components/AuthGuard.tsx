"use client";

import { Suspense, useEffect } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { consumeLogoutReason } from "@/lib/authSessionManager";

type AuthGuardProps = {
  children: React.ReactNode;
};

function AuthGuardInner({ children }: AuthGuardProps) {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  useEffect(() => {
    if (isLoading) return;
    if (isAuthenticated) return;
    if (pathname === "/login") return;
    const logoutReason = consumeLogoutReason();
    const q = searchParams.toString();
    const here = q ? `${pathname}?${q}` : pathname;
    const next = new URLSearchParams({ returnUrl: here });
    if (logoutReason && logoutReason !== "user_logout") {
      next.set("reason", "session_expired");
    }
    router.replace(`/login?${next.toString()}`);
  }, [isAuthenticated, isLoading, router, pathname, searchParams]);

  if (isLoading || !isAuthenticated) {
    return (
      <main className="mx-auto max-w-lg px-4 py-16 text-center text-sm text-neutral-500">
        Checking session…
      </main>
    );
  }

  return <>{children}</>;
}

const fallback = (
  <main className="mx-auto max-w-lg px-4 py-16 text-center text-sm text-neutral-500">
    Checking session…
  </main>
);

/**
 * Client-side route protection. Redirects to `/login` when not authenticated.
 */
export function AuthGuard(props: AuthGuardProps) {
  return (
    <Suspense fallback={fallback}>
      <AuthGuardInner {...props} />
    </Suspense>
  );
}
