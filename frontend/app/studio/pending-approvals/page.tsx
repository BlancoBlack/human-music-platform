"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AuthGuard } from "@/components/AuthGuard";
import { StudioApprovalStatusBadge } from "@/components/studio/StudioApprovalStatusBadge";
import {
  API_BASE,
  fetchStudioPendingApprovalsList,
  type StudioPendingListItem,
} from "@/lib/api";

function PendingApprovalsPageInner() {
  const [items, setItems] = useState<StudioPendingListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void fetchStudioPendingApprovalsList()
      .then((data) => {
        if (!cancelled) {
          setItems(data);
          setError(null);
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setItems([]);
          setError(
            e instanceof Error ? e.message : "Could not load pending approvals.",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Pending approvals</h1>
        <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-400">
          Review releases that need your royalty or feature approval.
        </p>
      </div>

      {items === null && !error && (
        <p className="text-sm text-neutral-500 dark:text-neutral-400">Loading…</p>
      )}

      {error && (
        <p
          className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-100"
          role="alert"
        >
          {error}
        </p>
      )}

      {items != null && items.length === 0 && !error && (
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          You have no pending approvals
        </p>
      )}

      {items != null && items.length > 0 && (
        <ul className="space-y-3" aria-label="Releases pending approval">
          {items.map((item) => {
            const coverSrc = item.release.cover_url
              ? `${API_BASE}${item.release.cover_url}`
              : null;
            return (
              <li key={item.release.id}>
                <Link
                  href={`/studio/releases/${item.release.id}`}
                  className="block rounded-xl border border-neutral-200 bg-white p-4 shadow-sm transition hover:border-neutral-300 hover:bg-neutral-50 dark:border-neutral-800 dark:bg-neutral-950 dark:hover:border-neutral-700 dark:hover:bg-neutral-900/60"
                >
                  <div className="flex gap-3">
                    <div className="h-16 w-16 shrink-0 overflow-hidden rounded-lg bg-neutral-200 dark:bg-neutral-800">
                      {coverSrc ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={coverSrc}
                          alt=""
                          className="h-full w-full object-cover"
                        />
                      ) : (
                        <div className="flex h-full w-full items-center justify-center text-xs text-neutral-500">
                          No cover
                        </div>
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="font-medium text-neutral-900 dark:text-neutral-100">
                          {item.release.title}
                        </p>
                        <StudioApprovalStatusBadge approvalStatus={item.approval_status} />
                      </div>
                      <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-400">
                        {item.release.artist.name}
                      </p>
                      <p className="mt-2 text-xs text-neutral-600 dark:text-neutral-400">
                        Split pending:{" "}
                        <span className="font-medium">{item.pending_summary.split}</span>
                        {" · "}
                        Feature pending:{" "}
                        <span className="font-medium">{item.pending_summary.feature}</span>
                      </p>
                    </div>
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </main>
  );
}

export default function PendingApprovalsPage() {
  return (
    <AuthGuard>
      <PendingApprovalsPageInner />
    </AuthGuard>
  );
}
