"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AuthGuard } from "@/components/AuthGuard";
import { StudioApprovalStatusBadge } from "@/components/studio/StudioApprovalStatusBadge";
import {
  API_BASE,
  fetchStudioReleaseDetail,
  postStudioReleaseApprove,
  postStudioReleaseReject,
  type StudioParticipant,
  type StudioReleaseDetail,
} from "@/lib/api";
import { buildParticipantViewModel } from "@/lib/participantViewModel";

function roleLabel(role: StudioParticipant["role"]): string {
  if (role === "primary") return "Primary";
  if (role === "collaborator") return "Collaborator";
  return "Featured";
}

function statusLabel(status: StudioParticipant["status"]): string {
  if (status === "accepted") return "Accepted";
  if (status === "rejected") return "Rejected";
  return "Pending";
}

function percentageLabel(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return `${(value * 100).toFixed(2).replace(/\.00$/, "")}%`;
}

function participantKey(participant: Pick<StudioParticipant, "artist_id" | "approval_type">): string {
  return `${participant.artist_id}-${participant.approval_type}`;
}

function StudioReleaseDetailInner() {
  const params = useParams<{ id: string }>();
  const releaseId = Number(params.id);
  const validReleaseId = Number.isFinite(releaseId) && releaseId > 0;

  const [detail, setDetail] = useState<StudioReleaseDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [busyMessage, setBusyMessage] = useState<string | null>(null);
  const [rejectReasonByKey, setRejectReasonByKey] = useState<
    Record<string, string>
  >({});

  const loadDetail = useCallback(async () => {
    if (!validReleaseId) return;
    const data = await fetchStudioReleaseDetail(releaseId);
    setDetail(data);
  }, [releaseId, validReleaseId]);

  useEffect(() => {
    if (!validReleaseId) return;
    let cancelled = false;
    void fetchStudioReleaseDetail(releaseId)
      .then((data) => {
        if (!cancelled) {
          setDetail(data);
          setError(null);
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setDetail(null);
          setError(
            e instanceof Error ? e.message : "Could not load release detail.",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [releaseId, validReleaseId]);

  const splitShareByArtistId = useMemo(() => {
    if (!detail) return new Map<number, number>();
    return new Map(detail.splits.map((s) => [s.artist_id, s.share]));
  }, [detail]);

  const participantVM = useMemo(
    () => buildParticipantViewModel(detail?.participants ?? []),
    [detail?.participants],
  );

  const readyWithFeaturePending = useMemo(() => {
    if (!detail) return false;
    if (detail.release.approval_status !== "ready") return false;
    return detail.participants.some(
      (p) => p.approval_type === "feature" && p.status !== "accepted",
    );
  }, [detail]);

  const handleApprove = async (participant: StudioParticipant) => {
    if (!validReleaseId) return;
    const key = participantKey(participant);
    setActionError(null);
    setBusyKey(key);
    setBusyMessage("Approving...");
    try {
      await postStudioReleaseApprove(releaseId, { artist_id: participant.artist_id });
      await loadDetail();
    } catch (e: unknown) {
      console.error("studio approve failed", e);
      setActionError("Something went wrong. Please try again.");
    } finally {
      setBusyKey(null);
      setBusyMessage(null);
    }
  };

  const handleReject = async (participant: StudioParticipant) => {
    if (!validReleaseId) return;
    const key = participantKey(participant);
    setActionError(null);
    setBusyKey(key);
    setBusyMessage("Rejecting...");
    try {
      await postStudioReleaseReject(releaseId, {
        artist_id: participant.artist_id,
        reason: rejectReasonByKey[key] || "",
      });
      await loadDetail();
    } catch (e: unknown) {
      console.error("studio reject failed", e);
      setActionError("Something went wrong. Please try again.");
    } finally {
      setBusyKey(null);
      setBusyMessage(null);
    }
  };

  if (!validReleaseId) {
    return (
      <main className="mx-auto max-w-3xl px-4 py-10">
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          Invalid release id.
        </p>
      </main>
    );
  }

  if (detail == null && error == null) {
    return (
      <main className="mx-auto max-w-3xl px-4 py-10">
        <p className="text-sm text-neutral-500 dark:text-neutral-400">Loading…</p>
      </main>
    );
  }

  if (error != null) {
    return (
      <main className="mx-auto max-w-3xl px-4 py-10">
        <p
          className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-100"
          role="alert"
        >
          {error}
        </p>
      </main>
    );
  }

  if (detail == null) return null;

  const coverSrc = detail.release.cover_url
    ? `${API_BASE}${detail.release.cover_url}`
    : null;

  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      <header className="mb-6 rounded-xl border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-950">
        <div className="flex gap-3">
          <div className="h-20 w-20 shrink-0 overflow-hidden rounded-lg bg-neutral-200 dark:bg-neutral-800">
            {coverSrc ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={coverSrc} alt="" className="h-full w-full object-cover" />
            ) : (
              <div className="flex h-full w-full items-center justify-center text-xs text-neutral-500">
                No cover
              </div>
            )}
          </div>
          <div className="min-w-0 flex-1">
            <h1 className="text-2xl font-semibold tracking-tight text-neutral-900 dark:text-neutral-100">
              {detail.release.title}
            </h1>
            <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-400">
              {detail.release.artist.name}
            </p>
            <div className="mt-2">
              <StudioApprovalStatusBadge
                approvalStatus={detail.release.approval_status}
                readyWithFeaturePending={readyWithFeaturePending}
              />
            </div>
          </div>
        </div>
      </header>

      <section className="mb-4">
        <p className="text-sm text-neutral-700 dark:text-neutral-300">
          You have {participantVM.counts.actionable} pending approvals
        </p>
      </section>

      {actionError != null && (
        <p
          className="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/40 dark:text-red-100"
          role="alert"
        >
          {actionError}
        </p>
      )}

      {participantVM.counts.actionable === 0 && (
        <p className="mb-4 rounded-lg border border-neutral-200 bg-neutral-50 px-3 py-2 text-sm text-neutral-700 dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-300">
          All your approvals are completed
        </p>
      )}

      <section>
        <h2 className="mb-3 text-lg font-semibold tracking-tight">Participants</h2>
        <ul className="space-y-3" aria-label="Release participants">
          {participantVM.orderedParticipants.map((participant) => {
            const key = participantKey(participant);
            const isBusy = busyKey === key;
            const share = splitShareByArtistId.get(participant.artist_id);
            return (
              <li
                key={`${participant.artist_id}-${participant.role}`}
                className="rounded-xl border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-950"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-medium text-neutral-900 dark:text-neutral-100">
                      {participant.artist_name}
                    </p>
                    <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-400">
                      {roleLabel(participant.role)} · {statusLabel(participant.status)}
                    </p>
                    <p className="mt-1 text-xs text-neutral-600 dark:text-neutral-400">
                      Share: {percentageLabel(share)}
                    </p>
                    {participant.approval_type === "split" &&
                      participant.has_feature_context && (
                        <p className="mt-1 text-xs text-neutral-600 dark:text-neutral-400">
                          This includes a featured appearance
                        </p>
                      )}
                    {participant.approval_type === "feature" && (
                      <p className="mt-1 text-xs text-neutral-600 dark:text-neutral-400">
                        Your name will be removed, but the song will still be published
                      </p>
                    )}
                    {participant.rejection_reason && (
                      <p className="mt-1 text-xs text-red-700 dark:text-red-300">
                        Rejection reason: {participant.rejection_reason}
                      </p>
                    )}
                    {isBusy && busyMessage != null && (
                      <p className="mt-1 text-xs text-neutral-600 dark:text-neutral-400">
                        {busyMessage}
                      </p>
                    )}
                  </div>

                  {participant.is_actionable_for_user && (
                    <div className="w-full max-w-xs space-y-2">
                      <input
                        type="text"
                        value={rejectReasonByKey[key] ?? ""}
                        onChange={(e) => {
                          const next = e.target.value;
                          setRejectReasonByKey((prev) => ({
                            ...prev,
                            [key]: next,
                          }));
                        }}
                        placeholder="Example: royalties incorrect, metadata needs fix..."
                        className="w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 placeholder:text-neutral-500 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100 dark:placeholder:text-neutral-500"
                        disabled={isBusy}
                      />
                      <div className="flex gap-2">
                        <button
                          type="button"
                          disabled={isBusy}
                          onClick={() => {
                            void handleApprove(participant);
                          }}
                          className="inline-flex flex-1 items-center justify-center rounded-md bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          {isBusy ? "Approving..." : "Approve"}
                        </button>
                        <button
                          type="button"
                          disabled={isBusy}
                          onClick={() => {
                            void handleReject(participant);
                          }}
                          className="inline-flex flex-1 items-center justify-center rounded-md bg-red-600 px-3 py-2 text-sm font-medium text-white hover:bg-red-500 disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          {isBusy ? "Rejecting..." : "Reject"}
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      </section>
    </main>
  );
}

export default function StudioReleaseDetailPage() {
  return (
    <AuthGuard>
      <StudioReleaseDetailInner />
    </AuthGuard>
  );
}
