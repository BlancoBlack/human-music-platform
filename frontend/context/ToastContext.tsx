"use client";

import Link from "next/link";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

type ToastKind = "success" | "error";

export type ToastRecord = {
  id: string;
  kind: ToastKind;
  message: string;
  /** Optional CTA (e.g. navigate after playlist add). */
  action?: { label: string; href: string };
};

export type ToastContextValue = {
  showSuccess: (
    message: string,
    opts?: { action?: { label: string; href: string } },
  ) => void;
  showError: (message: string) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

const TOAST_MS = 2000;
const TOAST_MS_WITH_ACTION = 4500;
/** Max simultaneous toasts; oldest dropped when exceeded. */
const MAX_VISIBLE_TOASTS = 2;

function makeId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function ToastItem({ toast }: { toast: ToastRecord }) {
  const [entered, setEntered] = useState(false);

  useEffect(() => {
    const id = requestAnimationFrame(() => setEntered(true));
    return () => cancelAnimationFrame(id);
  }, []);

  const palette =
    toast.kind === "success"
      ? "border-emerald-400/35 bg-emerald-950/95 text-emerald-50 shadow-emerald-900/20"
      : "border-rose-400/35 bg-rose-950/95 text-rose-50 shadow-rose-900/20";

  return (
    <div
      className={`rounded-lg border px-3.5 py-2.5 text-sm shadow-lg backdrop-blur-sm transition-all duration-300 ease-out ${palette} ${
        entered ? "translate-y-0 opacity-100" : "translate-y-2 opacity-0"
      }`}
      role="status"
    >
      <p className="leading-snug">{toast.message}</p>
      {toast.action ? (
        <Link
          href={toast.action.href}
          className="mt-2 inline-flex rounded-md bg-emerald-500/25 px-3 py-1 text-xs font-semibold text-emerald-100 ring-1 ring-emerald-400/40 transition-colors duration-150 hover:bg-emerald-500/35"
        >
          {toast.action.label}
        </Link>
      ) : null}
    </div>
  );
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastRecord[]>([]);

  const remove = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const push = useCallback(
    (
      kind: ToastKind,
      message: string,
      extra?: { action?: { label: string; href: string } },
    ) => {
      const id = makeId();
      const text =
        message.trim() ||
        (kind === "success" ? "Done" : "Something went wrong");
      const action = kind === "success" ? extra?.action : undefined;
      const entry: ToastRecord = { id, kind, message: text, action };
      setToasts((prev) => {
        const combined = [...prev, entry];
        return combined.length > MAX_VISIBLE_TOASTS
          ? combined.slice(-MAX_VISIBLE_TOASTS)
          : combined;
      });
      const ms =
        kind === "success" && action ? TOAST_MS_WITH_ACTION : TOAST_MS;
      window.setTimeout(() => remove(id), ms);
    },
    [remove],
  );

  const showSuccess = useCallback(
    (
      message: string,
      opts?: { action?: { label: string; href: string } },
    ) => push("success", message, opts),
    [push],
  );
  const showError = useCallback(
    (message: string) => push("error", message),
    [push],
  );

  const value = useMemo(
    () => ({ showSuccess, showError }),
    [showSuccess, showError],
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        className="pointer-events-none fixed bottom-6 left-1/2 z-[120] flex w-[min(100vw-2rem,28rem)] -translate-x-1/2 flex-col items-stretch gap-2 px-4"
        aria-live="polite"
      >
        {toasts.map((t) => (
          <div key={t.id} className="pointer-events-auto">
            <ToastItem toast={t} />
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used within ToastProvider");
  }
  return ctx;
}
