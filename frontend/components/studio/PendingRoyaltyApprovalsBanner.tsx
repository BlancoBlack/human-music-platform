"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { fetchStudioPendingApprovalsList } from "@/lib/api";
import { buildParticipantViewModel } from "@/lib/participantViewModel";

export function PendingRoyaltyApprovalsBanner() {
  const [pendingCount, setPendingCount] = useState<number>(0);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void fetchStudioPendingApprovalsList()
      .then((items) => {
        if (cancelled) return;
        const count = items.reduce((acc, item) => {
          const vm = buildParticipantViewModel(
            item.participants.map((p) => ({
              ...p,
              requires_approval: p.status === "pending",
              has_feature_context: false,
              rejection_reason: null,
              approved_at: null,
            })),
          );
          return acc + vm.counts.actionable;
        }, 0);
        setPendingCount(count);
        setVisible(count > 0);
      })
      .catch(() => {
        if (!cancelled) {
          setPendingCount(0);
          setVisible(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!visible) return null;

  return (
    <div
      className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 dark:border-amber-900 dark:bg-amber-950/40"
      role="status"
      aria-live="polite"
    >
      <p className="text-sm font-medium text-amber-900 dark:text-amber-100">
        You have {pendingCount} pending royalty approvals
      </p>
      <Link
        href="/studio/pending-approvals"
        className="rounded-md border border-amber-300 bg-white px-3 py-1.5 text-sm font-medium text-amber-900 hover:bg-amber-100 dark:border-amber-700 dark:bg-amber-900/20 dark:text-amber-100 dark:hover:bg-amber-900/40"
      >
        Set royalties
      </Link>
    </div>
  );
}
