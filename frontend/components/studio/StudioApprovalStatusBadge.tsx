"use client";

type ApprovalStatus = "draft" | "pending_approvals" | "ready";

export function StudioApprovalStatusBadge({
  approvalStatus,
  readyWithFeaturePending = false,
}: {
  approvalStatus: ApprovalStatus;
  readyWithFeaturePending?: boolean;
}) {
  if (approvalStatus === "ready") {
    return (
      <span className="rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-medium text-emerald-900 dark:bg-emerald-900/40 dark:text-emerald-100">
        {readyWithFeaturePending
          ? "Ready for release (some featured artists haven't responded yet)"
          : "Ready for release"}
      </span>
    );
  }
  if (approvalStatus === "pending_approvals") {
    return (
      <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-900 dark:bg-amber-900/40 dark:text-amber-100">
        Pending approvals
      </span>
    );
  }
  return (
    <span className="rounded-full bg-neutral-100 px-2.5 py-0.5 text-xs font-medium text-neutral-700 dark:bg-neutral-800 dark:text-neutral-300">
      Draft
    </span>
  );
}
