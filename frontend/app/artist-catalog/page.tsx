"use client";

import Link from "next/link";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ArtistHubNav } from "@/components/ArtistHubNav";
import { useAudioPlayer } from "@/components/audio/AudioPlayerProvider";
import {
  API_BASE,
  fetchArtistSongs,
  type ArtistCatalogSong,
} from "@/lib/api";

function formatDurationMmSs(seconds: number | null | undefined): string {
  if (seconds == null || seconds < 0 || !Number.isFinite(seconds)) {
    return "--:--";
  }
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/** Display order only; API order is preserved within each bucket via stable sort. */
function catalogSortRank(song: ArtistCatalogSong): number {
  if (song.playable) return 0;
  const st = song.upload_status;
  if (st === "audio_uploaded" || st === "cover_uploaded") return 1;
  if (st === "draft") return 2;
  return 3;
}

function sortCatalogSongs(songs: ArtistCatalogSong[]): ArtistCatalogSong[] {
  return [...songs]
    .map((s, index) => ({ s, index }))
    .sort((a, b) => {
      const ra = catalogSortRank(a.s);
      const rb = catalogSortRank(b.s);
      if (ra !== rb) return ra - rb;
      return a.index - b.index;
    })
    .map(({ s }) => s);
}

function formatStatusLabel(uploadStatus: string): string {
  switch (uploadStatus) {
    case "draft":
      return "Draft";
    case "audio_uploaded":
      return "Audio uploaded";
    case "cover_uploaded":
      return "Cover uploaded";
    case "ready":
      return "Ready";
    default:
      return uploadStatus;
  }
}

function CoverPlaceholder() {
  return (
    <div
      className="flex h-full w-full items-center justify-center text-neutral-400 dark:text-neutral-500"
      aria-hidden
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 24 24"
        fill="currentColor"
        className="h-7 w-7 opacity-90"
      >
        <path d="M12 3v9.55A4 4 0 1 0 14 17V7h4V3h-6z" />
      </svg>
    </div>
  );
}

const uploadBaseHref = (artistId: number) =>
  `/artist-upload?artist_id=${artistId}`;

function catalogContinueAction(
  song: ArtistCatalogSong,
  artistId: number,
): { label: string; href: string } | null {
  if (song.playable) return null;
  const href = uploadBaseHref(artistId);
  switch (song.upload_status) {
    case "draft":
      return { label: "Continue upload", href };
    case "audio_uploaded":
      return { label: "Add cover", href };
    case "cover_uploaded":
      return { label: "Finish upload", href };
    default:
      return null;
  }
}

function statusBadgeClass(status: string): string {
  const base =
    "rounded-full px-2.5 py-0.5 text-xs font-medium tracking-wide";
  switch (status) {
    case "ready":
      return `${base} bg-emerald-100 text-emerald-900 dark:bg-emerald-900/40 dark:text-emerald-100`;
    case "draft":
      return `${base} bg-neutral-100 text-neutral-700 dark:bg-neutral-800 dark:text-neutral-300`;
    case "audio_uploaded":
      return `${base} bg-sky-100 text-sky-900 dark:bg-sky-900/40 dark:text-sky-100`;
    case "cover_uploaded":
      return `${base} bg-violet-100 text-violet-900 dark:bg-violet-900/40 dark:text-violet-100`;
    default:
      return `${base} bg-amber-100 text-amber-950 dark:bg-amber-900/40 dark:text-amber-100`;
  }
}

function ArtistCatalogInner() {
  const searchParams = useSearchParams();
  const raw = searchParams.get("artist_id");
  const aid = raw ? parseInt(raw, 10) : NaN;
  const artistValid = Number.isFinite(aid) && aid > 0;
  const { playTrack, currentTrack, isPlaying, togglePlayback } =
    useAudioPlayer();

  const [songs, setSongs] = useState<ArtistCatalogSong[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [playError, setPlayError] = useState<string | null>(null);

  useEffect(() => {
    if (!artistValid) {
      setSongs(null);
      setLoadError(null);
      return;
    }
    let cancelled = false;
    setSongs(null);
    setLoadError(null);
    void fetchArtistSongs(aid)
      .then((data) => {
        if (!cancelled) setSongs(data.songs ?? []);
      })
      .catch((e) => {
        if (!cancelled) {
          setSongs(null);
          setLoadError(
            e instanceof Error ? e.message : "Could not load catalog.",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [artistValid, aid]);

  const displaySongs = useMemo(
    () => (songs != null ? sortCatalogSongs(songs) : []),
    [songs],
  );

  const playableQueue = useMemo(
    () =>
      displaySongs
        .filter((s) => s.playable && s.audio_url)
        .map((s) => ({
          id: s.id,
          title: s.title?.trim() ? s.title : "Untitled",
          audioUrl: `${API_BASE}${s.audio_url!}`,
          ...(s.cover_url != null
            ? { coverUrl: `${API_BASE}${s.cover_url}` }
            : {}),
        })),
    [displaySongs],
  );

  const handleCatalogRowActivate = (song: ArtistCatalogSong) => {
    if (!song.audio_url) return;
    setPlayError(null);
    if (currentTrack?.id === song.id) {
      void togglePlayback();
      return;
    }
    const idx = playableQueue.findIndex((t) => t.id === song.id);
    if (idx < 0) return;
    void playTrack(playableQueue[idx], {
      queue: playableQueue,
      queueIndex: idx,
    }).catch((e) => {
      setPlayError(
        e instanceof Error ? e.message : "Could not start playback.",
      );
    });
  };

  if (!artistValid) {
    return (
      <main className="mx-auto max-w-2xl px-4 py-10">
        <h1 className="text-xl font-semibold tracking-tight">Catalog</h1>
        <div
          className="mt-6 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-100"
          role="alert"
        >
          <p className="font-medium">Missing artist</p>
          <p className="mt-2 text-amber-900/90 dark:text-amber-100/90">
            Add a valid{" "}
            <code className="rounded bg-amber-100/80 px-1 dark:bg-amber-900/50">
              artist_id
            </code>{" "}
            to the URL (e.g.{" "}
            <code className="rounded bg-amber-100/80 px-1 dark:bg-amber-900/50">
              ?artist_id=1
            </code>
            ).
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-2xl px-4 py-10">
      <ArtistHubNav artistId={aid} active="catalog" />
      <div className="mb-8 flex items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold tracking-tight">Your catalog</h1>
        <Link
          href={uploadBaseHref(aid)}
          className="text-sm text-neutral-600 underline-offset-4 hover:underline dark:text-neutral-400"
        >
          Upload
        </Link>
      </div>

      {loadError && (
        <p
          className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-100"
          role="alert"
        >
          {loadError}
        </p>
      )}

      {playError && (
        <p
          className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-100"
          role="alert"
        >
          {playError}
        </p>
      )}

      {songs === null && loadError == null && (
        <p className="text-sm text-neutral-500 dark:text-neutral-400">
          Loading…
        </p>
      )}

      {songs !== null && songs.length === 0 && loadError == null && (
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          No songs yet. Upload your first track.
        </p>
      )}

      {songs !== null && songs.length > 0 && loadError == null && (
        <ul className="space-y-3" aria-label="Songs">
          {displaySongs.map((song) => {
            const coverSrc =
              song.cover_url != null
                ? `${API_BASE}${song.cover_url}`
                : null;
            const isCurrent = currentTrack?.id === song.id;
            const continueAction = catalogContinueAction(song, aid);
            const displayTitle = song.title?.trim() ? song.title : "Untitled";

            const rowClass = song.playable
              ? `rounded-xl border border-neutral-200 bg-white p-3 shadow-sm transition duration-150 hover:scale-[1.01] hover:border-neutral-300 hover:bg-neutral-50 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-neutral-400 dark:border-neutral-800 dark:bg-neutral-950 dark:hover:border-neutral-700 dark:hover:bg-neutral-900/60 dark:focus-visible:ring-neutral-500 ${
                  isCurrent
                    ? "cursor-pointer ring-2 ring-emerald-500/50 dark:ring-emerald-400/40"
                    : "cursor-pointer"
                }`
              : "rounded-xl border border-neutral-200 bg-neutral-50/80 p-3 dark:border-neutral-800 dark:bg-neutral-900/40";

            return (
              <li key={song.id}>
                <div
                  className={rowClass}
                  role={song.playable ? "button" : undefined}
                  tabIndex={song.playable ? 0 : undefined}
                  onClick={
                    song.playable
                      ? () => handleCatalogRowActivate(song)
                      : undefined
                  }
                  onKeyDown={
                    song.playable
                      ? (e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            handleCatalogRowActivate(song);
                          }
                        }
                      : undefined
                  }
                >
                  <div className="flex gap-3">
                    <div className="relative h-16 w-16 shrink-0 overflow-hidden rounded-lg bg-neutral-200 dark:bg-neutral-800">
                      {coverSrc ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={coverSrc}
                          alt=""
                          className="h-full w-full object-cover"
                        />
                      ) : (
                        <CoverPlaceholder />
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="font-medium text-neutral-900 dark:text-neutral-100">
                        {song.title || "Untitled"}
                      </p>
                      <p className="mt-1 font-mono text-sm tabular-nums text-neutral-500 dark:text-neutral-400">
                        {formatDurationMmSs(song.duration_seconds)}
                      </p>
                      <p className="mt-2 flex flex-wrap items-center gap-2">
                        <span className={statusBadgeClass(song.upload_status)}>
                          {formatStatusLabel(song.upload_status)}
                        </span>
                        {continueAction != null && (
                          <Link
                            href={continueAction.href}
                            className="inline-flex cursor-pointer items-center rounded-lg border border-neutral-300 bg-white px-3 py-1.5 text-xs font-medium text-neutral-800 shadow-sm transition hover:bg-neutral-50 dark:border-neutral-600 dark:bg-neutral-800 dark:text-neutral-100 dark:hover:bg-neutral-700"
                            onClick={(e) => e.stopPropagation()}
                          >
                            {continueAction.label}
                          </Link>
                        )}
                      </p>
                    </div>
                    {song.playable && (
                      <div className="flex shrink-0 items-center self-center">
                        <button
                          type="button"
                          className="flex h-10 w-10 cursor-pointer items-center justify-center rounded-full bg-neutral-900 text-white shadow-sm transition hover:scale-105 hover:bg-neutral-800 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-white"
                          aria-label={
                            isCurrent && isPlaying
                              ? `Pause ${displayTitle}`
                              : `Play ${displayTitle}`
                          }
                          onClick={(e) => {
                            e.stopPropagation();
                            handleCatalogRowActivate(song);
                          }}
                        >
                          {isCurrent && isPlaying ? (
                            <svg
                              xmlns="http://www.w3.org/2000/svg"
                              viewBox="0 0 24 24"
                              fill="currentColor"
                              className="h-5 w-5"
                              aria-hidden
                            >
                              <path d="M6 5h4v14H6V5zm8 0h4v14h-4V5z" />
                            </svg>
                          ) : (
                            <svg
                              xmlns="http://www.w3.org/2000/svg"
                              viewBox="0 0 24 24"
                              fill="currentColor"
                              className="h-5 w-5 pl-0.5"
                              aria-hidden
                            >
                              <path d="M8 5v14l11-7L8 5z" />
                            </svg>
                          )}
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </main>
  );
}

export default function ArtistCatalogPage() {
  return (
    <Suspense
      fallback={
        <main className="mx-auto max-w-2xl px-4 py-10">
          <p className="text-sm text-neutral-500">Loading…</p>
        </main>
      }
    >
      <ArtistCatalogInner />
    </Suspense>
  );
}
