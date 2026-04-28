"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useAudioPlayer } from "@/components/audio/AudioPlayerProvider";
import { useAuth } from "@/context/AuthContext";
import {
  API_BASE,
  fetchStudioCatalog,
  fetchStudioMe,
  type StudioCatalogRelease,
  type StudioCatalogSort,
  type StudioCatalogTrack,
} from "@/lib/api";

const INITIAL_TRACK_COUNT = 6;
const LOAD_MORE_STEP = 6;

function capitalize(value: string): string {
  if (!value) return value;
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function formatDuration(value: number | null): string {
  if (value == null || !Number.isFinite(value) || value <= 0) return "--:--";
  const total = Math.floor(value);
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function ReleaseGrid({ releases }: { releases: StudioCatalogRelease[] }) {
  if (!releases.length) {
    return (
      <section className="mb-10 space-y-2">
        <h2 className="text-lg font-medium text-neutral-900 dark:text-white">Releases</h2>
        <p className="text-sm text-neutral-500 dark:text-neutral-400">Your catalog is empty</p>
      </section>
    );
  }

  return (
    <section className="mb-10 space-y-4">
      <h2 className="text-lg font-medium text-neutral-900 dark:text-white">Releases</h2>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {releases.slice(0, 5).map((release) => {
          const cover = release.cover_url ? `${API_BASE}${release.cover_url}` : null;
          return (
            <div
              key={`release-${release.id}`}
              className="group relative aspect-square overflow-hidden bg-neutral-200 dark:bg-neutral-900"
            >
              <Link
                href={`/album/${release.slug}`}
                className="absolute inset-0 block"
                aria-label={`Open ${release.title}`}
              >
                {cover ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={cover}
                    alt={release.title}
                    className="h-full w-full object-cover transition duration-300 group-hover:scale-105"
                  />
                ) : (
                  <div className="flex h-full w-full items-center justify-center text-xs text-neutral-500 dark:text-neutral-500">
                    Add cover
                  </div>
                )}

                <div className="pointer-events-none absolute inset-0 bg-black/0 transition duration-300 group-hover:bg-black/45" />
                <div className="pointer-events-none absolute inset-0 flex items-center justify-center opacity-0 transition duration-300 group-hover:opacity-100">
                  <div className="flex h-12 w-12 items-center justify-center rounded-full bg-white text-black">
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      viewBox="0 0 24 24"
                      fill="currentColor"
                      className="h-6 w-6 pl-0.5"
                      aria-hidden
                    >
                      <path d="M8 5v14l11-7L8 5z" />
                    </svg>
                  </div>
                </div>
              </Link>

              <Link
                href={`/studio/release/${release.id}/edit`}
                className="absolute right-2 top-2 z-10 text-xs text-white opacity-0 transition-opacity duration-150 group-hover:opacity-100"
              >
                Edit
              </Link>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function TrackRow({ track }: { track: StudioCatalogTrack }) {
  const { authReady, isAuthenticated } = useAuth();
  const { playTrack, currentTrack, isPlaying, togglePlayback } = useAudioPlayer();

  const displayTitle = track.title?.trim() ? track.title : "Untitled";
  const coverSrc = track.cover_url ? `${API_BASE}${track.cover_url}` : null;
  const canPlay = Boolean(track.playable && track.audio_url && authReady && isAuthenticated);
  const isCurrent = currentTrack?.id === track.id;

  const handleActivate = useCallback(() => {
    if (!canPlay || !track.audio_url) return;
    if (currentTrack?.id === track.id) {
      void togglePlayback();
      return;
    }
    const payload = {
      id: track.id,
      title: displayTitle,
      audioUrl: `${API_BASE}${track.audio_url}`,
      ...(track.cover_url ? { coverUrl: `${API_BASE}${track.cover_url}` } : {}),
    };
    void playTrack(payload, { queue: [payload], queueIndex: 0 }).catch((e) => {
      console.error("studio catalog play failed", e);
    });
  }, [
    canPlay,
    currentTrack?.id,
    displayTitle,
    playTrack,
    togglePlayback,
    track.audio_url,
    track.cover_url,
    track.id,
  ]);

  return (
    <li className="flex items-center gap-3 py-2">
      <div className="h-10 w-10 shrink-0 overflow-hidden bg-neutral-200 dark:bg-neutral-900">
        {coverSrc ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={coverSrc} alt="" className="h-full w-full object-cover" />
        ) : null}
      </div>

      <div className="min-w-0 flex-1">
        <Link
          href={`/track/${track.slug}`}
          className="block truncate text-sm font-medium text-neutral-900 hover:text-neutral-700 dark:text-neutral-100 dark:hover:text-white"
        >
          {displayTitle}
        </Link>
        <p className="truncate text-xs text-neutral-500 dark:text-neutral-400">{track.artist_name}</p>
      </div>

      <span className="w-12 shrink-0 text-right text-xs text-neutral-500 dark:text-neutral-400">
        {formatDuration(track.duration_seconds)}
      </span>

      <button
        type="button"
        onClick={handleActivate}
        disabled={!canPlay}
        className={
          canPlay
            ? "flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-neutral-900 text-white transition hover:bg-neutral-800 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-white"
            : "flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-neutral-200 text-neutral-400 dark:bg-neutral-800 dark:text-neutral-600"
        }
        aria-label={
          !canPlay
            ? `Not playable: ${displayTitle}`
            : isCurrent && isPlaying
              ? `Pause ${displayTitle}`
              : `Play ${displayTitle}`
        }
      >
        {isCurrent && isPlaying ? (
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="currentColor"
            className="h-4 w-4"
            aria-hidden
          >
            <path d="M6 5h4v14H6V5zm8 0h4v14h-4V5z" />
          </svg>
        ) : (
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="currentColor"
            className="h-4 w-4 pl-0.5"
            aria-hidden
          >
            <path d="M8 5v14l11-7L8 5z" />
          </svg>
        )}
      </button>
    </li>
  );
}

function TrackListSection({
  artistId,
}: {
  artistId: number | null;
}) {
  const [sort, setSort] = useState<StudioCatalogSort>("top");
  const [tracks, setTracks] = useState<StudioCatalogTrack[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [visibleCount, setVisibleCount] = useState(INITIAL_TRACK_COUNT);


  useEffect(() => {
    if (artistId == null) {
      setTracks([]);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    void fetchStudioCatalog(artistId, sort)
      .then((catalog) => {
        if (!cancelled) {
          setTracks(catalog.tracks);
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Failed to load tracks");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [artistId, sort]);

  const visibleTracks = useMemo(() => tracks.slice(0, visibleCount), [tracks, visibleCount]);
  const canLoadMore = visibleCount < tracks.length;

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <h2 className="text-lg font-medium text-neutral-900 dark:text-white">Tracks</h2>
        <div className="flex items-center gap-4 text-sm">
          <button
            type="button"
            onClick={() => setSort("top")}
            className={sort === "top" ? "text-neutral-900 dark:text-white" : "text-neutral-500 dark:text-neutral-400"}
          >
            Top
          </button>
          <button
            type="button"
            onClick={() => setSort("new")}
            className={sort === "new" ? "text-neutral-900 dark:text-white" : "text-neutral-500 dark:text-neutral-400"}
          >
            New
          </button>
          <button
            type="button"
            onClick={() => setSort("old")}
            className={sort === "old" ? "text-neutral-900 dark:text-white" : "text-neutral-500 dark:text-neutral-400"}
          >
            Old
          </button>
        </div>
      </div>

      {error ? (
        <p className="text-sm text-red-600 dark:text-red-400" role="alert">
          {error}
        </p>
      ) : null}

      {tracks.length === 0 && !loading ? (
        <p className="text-sm text-neutral-500 dark:text-neutral-400">No tracks available</p>
      ) : null}

      {visibleTracks.length > 0 ? (
        <div className={loading ? "opacity-60 transition-opacity" : "opacity-100 transition-opacity"}>
          <ul className="divide-y divide-neutral-200/70 dark:divide-neutral-800">
            {visibleTracks.map((track) => (
              <TrackRow key={`track-${track.id}`} track={track} />
            ))}
          </ul>

          <div className="mt-3 flex items-center gap-4">
            {canLoadMore ? (
              <button
                type="button"
                onClick={() => setVisibleCount((n) => n + LOAD_MORE_STEP)}
                className="text-sm text-neutral-900 hover:underline dark:text-white"
              >
                Load more
              </button>
            ) : null}
            {loading ? (
              <p className="text-xs text-neutral-500 dark:text-neutral-400">Updating tracks...</p>
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}

export default function StudioCatalogPage() {
  const { authReady, isAuthenticated } = useAuth();
  const [artistId, setArtistId] = useState<number | null>(null);
  const [artistName, setArtistName] = useState<string>("");
  const [releases, setReleases] = useState<StudioCatalogRelease[]>([]);
  const [loadingPage, setLoadingPage] = useState(false);
  const [pageError, setPageError] = useState<string | null>(null);

  useEffect(() => {
    if (!authReady || !isAuthenticated) {
      setArtistId(null);
      setArtistName("");
      setReleases([]);
      setPageError(null);
      return;
    }

    let cancelled = false;
    setLoadingPage(true);
    setPageError(null);

    void (async () => {
      try {
        const me = await fetchStudioMe();
        let resolvedArtistId: number | null = null;
        let resolvedArtistName = "";

        if (me.current_context?.type === "artist") {
          resolvedArtistId = Number(me.current_context.id);
          const match = me.allowed_contexts.artists.find(
            (artist) => Number(artist.id) === resolvedArtistId,
          );
          resolvedArtistName = match?.name || "";
        }

        if (resolvedArtistId == null && me.allowed_contexts.artists.length > 0) {
          const first = me.allowed_contexts.artists[0];
          resolvedArtistId = Number(first.id);
          resolvedArtistName = first.name || "";
        }

        if (resolvedArtistId == null) {
          if (!cancelled) {
            setArtistId(null);
            setArtistName("");
            setReleases([]);
          }
          return;
        }

        const catalog = await fetchStudioCatalog(resolvedArtistId, "top");

        if (!cancelled) {
          setArtistId(resolvedArtistId);
          setArtistName(capitalize(String(resolvedArtistName).trim()));
          setReleases(catalog.releases);
        }
      } catch (e) {
        if (!cancelled) {
          setPageError(e instanceof Error ? e.message : "Failed to load catalog");
          setArtistId(null);
          setArtistName("");
          setReleases([]);
        }
      } finally {
        if (!cancelled) setLoadingPage(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [authReady, isAuthenticated]);

  const title = artistName ? `${artistName}'s Catalog` : "Catalog";

  return (
    <main className="mx-auto max-w-7xl px-4 py-10">
      <header className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      </header>

      {loadingPage ? <p className="mb-8 text-sm text-neutral-500 dark:text-neutral-400">Loading...</p> : null}
      {pageError ? (
        <p className="mb-8 text-sm text-red-600 dark:text-red-400" role="alert">
          {pageError}
        </p>
      ) : null}

      {!loadingPage && !pageError ? <ReleaseGrid releases={releases} /> : null}

      {!loadingPage && !pageError ? <TrackListSection artistId={artistId} /> : null}
    </main>
  );
}
