"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { UploadWizardPageLayout } from "@/components/UploadWizardPageLayout";
import {
  fetchReleaseTracks,
  postStudioReleasePublish,
  type ReleaseTrackRow,
  type ReleaseTracksResponse,
} from "@/lib/api";

type Props = {
  releaseId: number;
  releaseTitle: string;
  headerSlot?: React.ReactNode;
  onAddTrack: (ctx: { trackIndex: number; trackCount: number }) => void;
  onEditTrack: (ctx: {
    songId: number;
    trackIndex: number;
    trackCount: number;
  }) => void;
};

function statusIcon(t: ReleaseTrackRow): string {
  if (t.completion_status === "complete") return "✔";
  if (t.completion_status === "empty") return "○";
  return "⚠";
}

export function AlbumTrackList({
  releaseId,
  releaseTitle,
  headerSlot,
  onAddTrack,
  onEditTrack,
}: Props) {
  const router = useRouter();
  const [data, setData] = useState<ReleaseTracksResponse | null>(null);
  const [publishBusy, setPublishBusy] = useState(false);
  const [publishError, setPublishError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      const d = await fetchReleaseTracks(releaseId);
      setData(d);
    } catch (e) {
      setData(null);
      setError(e instanceof Error ? e.message : "Failed to load tracks.");
    } finally {
      setLoading(false);
    }
  }, [releaseId]);

  useEffect(() => {
    void load();
  }, [load]);

  const publishAlbum = useCallback(async () => {
    setPublishError(null);
    setPublishBusy(true);
    try {
      await postStudioReleasePublish(releaseId);
      router.push("/studio/catalog");
    } catch (e) {
      setPublishError(
        e instanceof Error ? e.message : "Could not publish album.",
      );
    } finally {
      setPublishBusy(false);
    }
  }, [releaseId, router]);

  const tracks = data?.tracks ?? [];
  const n = tracks.length;
  const nextIndex = Math.max(n + 1, 1);
  const nextCount = Math.max(n + 1, 1);
  const totalTracks = data?.progress.total_tracks ?? 0;
  const incompleteTracks = data?.progress.incomplete_tracks ?? 0;
  const emptyTracks = data?.progress.empty_tracks ?? 0;
  const minimumTracksMissing = Math.max(0, 2 - totalTracks);
  const albumReadyForPublish =
    totalTracks >= 2 && incompleteTracks === 0 && emptyTracks === 0;

  return (
    <UploadWizardPageLayout>
      {headerSlot}
      <h1 className="mb-1 text-2xl font-semibold tracking-tight">Album tracks</h1>
      <p className="mb-6 text-sm text-neutral-600 dark:text-neutral-400">
        <span className="font-medium text-neutral-800 dark:text-neutral-200">
          {releaseTitle}
        </span>
        <span className="mx-2 text-neutral-400">·</span>
        Release ID {releaseId}
      </p>

      {loading && (
        <p className="text-sm text-neutral-500" aria-live="polite">
          Loading tracks…
        </p>
      )}
      {error && (
        <p className="mb-4 text-sm text-red-600 dark:text-red-400" role="alert">
          {error}
        </p>
      )}

      {!loading && data && (
        <section className="rounded-xl border border-neutral-200 p-6 dark:border-neutral-800">
          <div className="mb-4 space-y-1 text-sm">
            <p className="text-neutral-700 dark:text-neutral-300">
              Tracks:{" "}
              <span className="font-medium text-neutral-900 dark:text-neutral-100">
                {data.progress.total_tracks}
              </span>
            </p>
            <p className="text-neutral-600 dark:text-neutral-400">
              {albumReadyForPublish
                ? "Your album is ready to publish."
                : minimumTracksMissing > 0
                  ? `Add at least ${minimumTracksMissing} more track${minimumTracksMissing === 1 ? "" : "s"} to publish.`
                  : "Complete all tracks to publish your album."}
            </p>
          </div>

          <ol className="space-y-3">
            {tracks.map((t, i) => (
              <li
                key={t.id}
                className="flex flex-wrap items-center justify-between gap-2 border-b border-neutral-100 pb-3 last:border-0 dark:border-neutral-800"
              >
                <div className="min-w-0 flex-1">
                  <span className="mr-2 font-mono text-xs text-neutral-500">
                    {i + 1}.
                  </span>
                  <span className="font-medium text-neutral-900 dark:text-neutral-100">
                    {t.title?.trim() || "Untitled track"}
                  </span>
                  <span className="ml-2 text-sm text-neutral-500">
                    {statusIcon(t)} {t.completion_status}
                  </span>
                </div>
                <button
                  type="button"
                  className="shrink-0 rounded-lg border border-neutral-300 px-3 py-1.5 text-sm font-medium dark:border-neutral-600"
                  onClick={() =>
                    onEditTrack({
                      songId: t.id,
                      trackIndex: i + 1,
                      trackCount: Math.max(tracks.length, 1),
                    })
                  }
                >
                  Edit
                </button>
              </li>
            ))}
          </ol>

          <div className="mt-6 flex flex-col gap-3 sm:flex-row">
            <button
              type="button"
              className="rounded-lg bg-neutral-900 px-4 py-2.5 text-sm font-medium text-white dark:bg-neutral-100 dark:text-neutral-900"
              onClick={() =>
                onAddTrack({ trackIndex: nextIndex, trackCount: nextCount })
              }
            >
              + Add track
            </button>
            <button
              type="button"
              className="rounded-lg border border-neutral-300 px-4 py-2.5 text-sm dark:border-neutral-600"
              onClick={() => void load()}
            >
              Refresh list
            </button>
            <button
              type="button"
              disabled={publishBusy}
              className="rounded-lg bg-[#F37D25] px-4 py-2.5 text-sm font-medium text-black disabled:opacity-60"
              onClick={() => {
                void publishAlbum();
              }}
            >
              {publishBusy ? "Publishing…" : "Publish album"}
            </button>
          </div>

          {publishError ? (
            <p className="mt-3 text-sm text-red-600 dark:text-red-400" role="alert">
              {publishError}
            </p>
          ) : null}

          <p className="mt-4 text-xs text-neutral-500 dark:text-neutral-400">
            Progress: {data.progress.completed_tracks} complete ·{" "}
            {data.progress.incomplete_tracks} incomplete ·{" "}
            {data.progress.empty_tracks} empty · {data.progress.total_tracks}{" "}
            total
          </p>
        </section>
      )}
    </UploadWizardPageLayout>
  );
}
