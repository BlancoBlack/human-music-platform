"use client";

import { Suspense, useEffect } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/context/AuthContext";

type AuthGuardProps = {
  children: React.ReactNode;
};

function AuthGuardInner({ children }: AuthGuardProps) {
  const { user, initializing } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  useEffect(() => {
    if (initializing) return;
    if (user) return;
    const q = searchParams.toString();
    const here = q ? `${pathname}?${q}` : pathname;
    router.replace(`/login?returnUrl=${encodeURIComponent(here)}`);
  }, [user, initializing, router, pathname, searchParams]);

  if (initializing || !user) {
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
