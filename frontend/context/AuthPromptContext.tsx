"use client";

import Link from "next/link";
import { createContext, useCallback, useContext, useMemo, useState } from "react";

type AuthPromptContextValue = {
  openAuthModal: () => void;
  closeAuthModal: () => void;
};

const AuthPromptContext = createContext<AuthPromptContextValue | null>(null);

export function AuthPromptProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);

  const openAuthModal = useCallback(() => {
    setOpen(true);
  }, []);

  const closeAuthModal = useCallback(() => {
    setOpen(false);
  }, []);

  const value = useMemo<AuthPromptContextValue>(
    () => ({ openAuthModal, closeAuthModal }),
    [openAuthModal, closeAuthModal],
  );

  return (
    <AuthPromptContext.Provider value={value}>
      {children}
      {open ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-sm rounded-lg bg-white p-5 shadow-xl dark:bg-neutral-900">
            <h3 className="text-base font-semibold text-neutral-900 dark:text-white">Log in to play</h3>
            <p className="mt-2 text-sm text-neutral-600 dark:text-neutral-300">
              Create an account or log in to play tracks.
            </p>
            <div className="mt-4 flex gap-2">
              <Link
                href="/login"
                onClick={closeAuthModal}
                className="inline-flex flex-1 items-center justify-center rounded-md bg-neutral-900 px-3 py-2 text-sm text-white hover:bg-neutral-800 dark:bg-white dark:text-neutral-900"
              >
                Log in
              </Link>
              <Link
                href="/register"
                onClick={closeAuthModal}
                className="inline-flex flex-1 items-center justify-center rounded-md border border-neutral-300 px-3 py-2 text-sm text-neutral-900 hover:bg-neutral-100 dark:border-neutral-700 dark:text-white dark:hover:bg-neutral-800"
              >
                Sign up
              </Link>
            </div>
            <button
              type="button"
              onClick={closeAuthModal}
              className="mt-3 w-full rounded-md px-3 py-2 text-sm text-neutral-600 hover:bg-neutral-100 dark:text-neutral-300 dark:hover:bg-neutral-800"
            >
              Continue browsing
            </button>
          </div>
        </div>
      ) : null}
    </AuthPromptContext.Provider>
  );
}

export function useAuthPrompt(): AuthPromptContextValue {
  const ctx = useContext(AuthPromptContext);
  if (!ctx) {
    throw new Error("useAuthPrompt must be used within AuthPromptProvider");
  }
  return ctx;
}
