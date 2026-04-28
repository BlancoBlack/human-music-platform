"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { GlobalArtistSearch } from "@/components/navigation/GlobalArtistSearch";
import { useAuth } from "@/context/AuthContext";

export function GlobalNavbar() {
  const router = useRouter();
  const { isAuthenticated, authReady, logout } = useAuth();

  const handleLogout = async () => {
    await logout();
    router.push("/login");
  };

  const linkClass =
    "font-medium text-neutral-700 hover:text-neutral-900 dark:text-neutral-300 dark:hover:text-neutral-100";
  return (
    <header className="border-b border-neutral-200 bg-white/90 backdrop-blur dark:border-neutral-800 dark:bg-neutral-950/90">
      <nav
        className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-x-6 gap-y-3 px-4 py-3"
        aria-label="Global navigation"
      >
        <div className="flex items-center text-sm">
          <Link
            href="/"
            className="text-base font-semibold tracking-[0.18em] text-neutral-900 dark:text-neutral-100"
            aria-label="SONUMA home"
          >
            SONUMA
          </Link>
        </div>

        <div className="flex items-center gap-4 text-sm">
          {!authReady ? (
            <span
              className="invisible inline-block font-medium"
              aria-hidden
            >
              Loading
            </span>
          ) : (
            <>
              <GlobalArtistSearch />

              <Link href="/discovery" className={linkClass}>
                Discovery
              </Link>

              {isAuthenticated ? (
                <>
                  <Link href="/studio" className={linkClass}>
                    Studio
                  </Link>

                  <button
                    type="button"
                    className="text-neutral-500 hover:text-neutral-800 dark:text-neutral-400 dark:hover:text-neutral-200"
                    aria-label="Settings"
                  >
                    Settings
                  </button>

                  <button
                    type="button"
                    onClick={handleLogout}
                    className={linkClass}
                  >
                    Logout
                  </button>
                </>
              ) : (
                <Link href="/login" className={linkClass}>
                  Login
                </Link>
              )}
            </>
          )}
        </div>
      </nav>
    </header>
  );
}
