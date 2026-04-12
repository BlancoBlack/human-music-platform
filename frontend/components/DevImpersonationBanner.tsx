"use client";

import { useAuth } from "@/context/AuthContext";

/**
 * Fixed banner when `/auth/me` reports an active dev impersonation session.
 */
export function DevImpersonationBanner() {
  const { user, isImpersonating, exitImpersonation } = useAuth();
  const imp = user?.impersonation;
  if (!isImpersonating || !imp || !user) {
    return null;
  }

  const targetLabel =
    user.display_name || user.email || `user #${String(user.id)}`;
  const actorLabel =
    imp.actor_email != null && imp.actor_email !== ""
      ? imp.actor_email
      : `user #${String(imp.actor_id)}`;

  return (
    <div
      className="sticky top-0 z-50 border-b border-amber-700/50 bg-amber-950 px-4 py-2 text-center text-sm text-amber-50"
      role="status"
    >
      <span className="font-medium">Impersonating</span>{" "}
      <span className="text-amber-200">{targetLabel}</span>
      <span className="text-amber-400/90"> (as {actorLabel})</span>
      <button
        type="button"
        onClick={() => void exitImpersonation()}
        className="ml-4 rounded border border-amber-400/60 px-2 py-0.5 text-xs font-medium text-amber-100 hover:bg-amber-900/80"
      >
        Exit impersonation
      </button>
    </div>
  );
}
