"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useAudioPlayer } from "@/components/audio/AudioPlayerProvider";
import {
  API_BASE,
  ApiNotFoundError,
  fetchArtist,
  fetchArtistSongs,
  fetchSong,
  type ArtistPublic,
  type SongDetail,
} from "@/lib/api";

function formatDurationMmSs(seconds: number | null | undefined): string {
  if (seconds == null || seconds < 0 || !Number.isFinite(seconds)) {
    return "--:--";
  }
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
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

const CATALOG_FETCH_LIMIT = 200;

type LoadState =
  | { kind: "loading" }
  | { kind: "not_found" }
  | { kind: "error"; message: string }
  | {
      kind: "ready";
      song: SongDetail;
      artist: ArtistPublic | null;
      audioUrl: string | null;
      playable: boolean;
    };

function SongPageInner() {
  const params = useParams();
  const rawId = params.id;
  const songId =
    typeof rawId === "string"
      ? parseInt(rawId, 10)
      : Array.isArray(rawId)
        ? parseInt(rawId[0] ?? "", 10)
        : NaN;

  const invalidId = !Number.isFinite(songId) || songId <= 0;

  const { playTrack, currentTrack, isPlaying, isBuffering, togglePlayback } =
    useAudioPlayer();

  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [playError, setPlayError] = useState<string | null>(null);

  useEffect(() => {
    if (invalidId) return;

    let cancelled = false;

    void (async () => {
      try {
        const song = await fetchSong(songId);
        if (cancelled) return;

        const [artistResult, catalogResult] = await Promise.allSettled([
          fetchArtist(song.artist_id),
          fetchArtistSongs(song.artist_id, CATALOG_FETCH_LIMIT),
        ]);

        if (cancelled) return;

        const artist =
          artistResult.status === "fulfilled" ? artistResult.value : null;

        let audioUrl: string | null = null;
        let playable = false;
        if (catalogResult.status === "fulfilled") {
          const row = catalogResult.value.songs?.find((s) => s.id === song.id);
          if (row) {
            audioUrl = row.audio_url;
            playable = row.playable === true && !!row.audio_url;
          }
        }

        setState({
          kind: "ready",
          song,
          artist,
          audioUrl,
          playable,
        });
      } catch (e) {
        if (cancelled) return;
        if (e instanceof ApiNotFoundError) {
          setState({ kind: "not_found" });
          return;
        }
        setState({
          kind: "error",
          message:
            e instanceof Error ? e.message : "Something went wrong loading this song.",
        });
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [invalidId, songId]);

  const handlePlay = useCallback(() => {
    if (state.kind !== "ready") return;
    const { song, audioUrl, playable } = state;
    if (!playable || !audioUrl) return;

    setPlayError(null);
    const displayTitle = song.title?.trim() ? song.title : "Untitled";
    const track = {
      id: song.id,
      title: displayTitle,
      audioUrl: `${API_BASE}${audioUrl}`,
      ...(song.cover_url != null
        ? { coverUrl: `${API_BASE}${song.cover_url}` }
        : {}),
    };

    if (currentTrack?.id === song.id) {
      void togglePlayback();
      return;
    }

    void playTrack(track).catch((err) => {
      setPlayError(
        err instanceof Error ? err.message : "Could not start playback.",
      );
    });
  }, [state, currentTrack?.id, playTrack, togglePlayback]);

  if (invalidId) {
    return (
      <main className="mx-auto max-w-lg px-4 py-12">
        <h1 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">
          Song not found
        </h1>
        <p className="mt-2 text-sm text-neutral-600 dark:text-neutral-400">
          Invalid song link.
        </p>
        <Link
          href="/"
          className="mt-6 inline-block text-sm font-medium text-neutral-700 underline-offset-4 hover:underline dark:text-neutral-300"
        >
          Back to home
        </Link>
      </main>
    );
  }

  if (state.kind === "loading") {
    return (
      <main className="mx-auto max-w-lg px-4 py-12">
        <p className="text-sm text-neutral-500 dark:text-neutral-400">
          Loading song…
        </p>
      </main>
    );
  }

  if (state.kind === "not_found") {
    return (
      <main className="mx-auto max-w-lg px-4 py-12">
        <h1 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">
          Song not found
        </h1>
        <p className="mt-2 text-sm text-neutral-600 dark:text-neutral-400">
          This song does not exist or may have been removed.
        </p>
        <Link
          href="/"
          className="mt-6 inline-block text-sm font-medium text-neutral-700 underline-offset-4 hover:underline dark:text-neutral-300"
        >
          Back to home
        </Link>
      </main>
    );
  }

  if (state.kind === "error") {
    return (
      <main className="mx-auto max-w-lg px-4 py-12">
        <h1 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">
          Could not load song
        </h1>
        <p className="mt-2 text-sm text-neutral-600 dark:text-neutral-400">
          {state.message}
        </p>
        <Link
          href="/"
          className="mt-6 inline-block text-sm font-medium text-neutral-700 underline-offset-4 hover:underline dark:text-neutral-300"
        >
          Back to home
        </Link>
      </main>
    );
  }

  const { song, artist, playable, audioUrl } = state;
  const displayTitle = song.title?.trim() ? song.title : "Untitled";
  const coverSrc =
    song.cover_url != null ? `${API_BASE}${song.cover_url}` : null;
  const isCurrent = currentTrack?.id === song.id;
  const showPause = isCurrent && isPlaying;

  return (
    <main className="mx-auto max-w-lg px-4 py-10">
      <div className="mb-8">
        <Link
          href={`/artist-catalog?artist_id=${song.artist_id}`}
          className="text-sm text-neutral-600 underline-offset-4 hover:underline dark:text-neutral-400"
        >
          ← Artist catalog
        </Link>
      </div>

      <article className="overflow-hidden rounded-2xl border border-neutral-200 bg-white shadow-sm dark:border-neutral-800 dark:bg-neutral-950">
        <div className="aspect-square w-full bg-neutral-200 dark:bg-neutral-800">
          {coverSrc ? (
            // eslint-disable-next-line @next/next/no-img-element -- API URL
            <img
              src={coverSrc}
              alt=""
              className="h-full w-full object-cover"
            />
          ) : (
            <div
              className="flex h-full w-full items-center justify-center text-neutral-400 dark:text-neutral-500"
              aria-hidden
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                fill="currentColor"
                className="h-20 w-20 opacity-90"
              >
                <path d="M12 3v9.55A4 4 0 1 0 14 17V7h4V3h-6z" />
              </svg>
            </div>
          )}
        </div>

        <div className="space-y-4 p-6">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-neutral-900 dark:text-neutral-100">
              {displayTitle}
            </h1>
            {artist != null && (
              <p className="mt-1 text-neutral-600 dark:text-neutral-400">
                {artist.name}
              </p>
            )}
            {artist == null && (
              <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-500">
                Artist #{song.artist_id}
              </p>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <span className={statusBadgeClass(song.upload_status)}>
              {formatStatusLabel(song.upload_status)}
            </span>
            <span className="font-mono text-sm tabular-nums text-neutral-500 dark:text-neutral-400">
              {formatDurationMmSs(song.duration_seconds)}
            </span>
          </div>

          {playError && (
            <p
              className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-100"
              role="alert"
            >
              {playError}
            </p>
          )}

          {!playable && (
            <p className="text-sm text-neutral-500 dark:text-neutral-400">
              Playback is available when the song is ready and master audio is
              uploaded.
            </p>
          )}

          <button
            type="button"
            disabled={!playable || !audioUrl || isBuffering}
            onClick={handlePlay}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-neutral-900 py-3.5 text-sm font-medium text-white transition hover:bg-neutral-800 disabled:cursor-not-allowed disabled:opacity-40 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-white dark:disabled:opacity-40"
            aria-label={
              showPause ? `Pause ${displayTitle}` : `Play ${displayTitle}`
            }
          >
            {isBuffering && isCurrent ? (
              <span
                className="inline-block h-5 w-5 shrink-0 animate-spin rounded-full border-2 border-white border-t-transparent dark:border-neutral-900 dark:border-t-transparent"
                aria-hidden
              />
            ) : showPause ? (
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                fill="currentColor"
                className="h-6 w-6"
                aria-hidden
              >
                <path d="M6 5h4v14H6V5zm8 0h4v14h-4V5z" />
              </svg>
            ) : (
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                fill="currentColor"
                className="h-6 w-6 pl-0.5"
                aria-hidden
              >
                <path d="M8 5v14l11-7L8 5z" />
              </svg>
            )}
            {showPause ? "Pause" : "Play"}
          </button>
        </div>
      </article>
    </main>
  );
}

function SongPageWithRemountKey() {
  const params = useParams();
  const raw = params.id;
  const remountKey =
    typeof raw === "string"
      ? raw
      : Array.isArray(raw)
        ? (raw[0] ?? "0")
        : "0";
  return <SongPageInner key={remountKey} />;
}

export default function SongPage() {
  return (
    <Suspense
      fallback={
        <main className="mx-auto max-w-lg px-4 py-12">
          <p className="text-sm text-neutral-500 dark:text-neutral-400">
            Loading song…
          </p>
        </main>
      }
    >
      <SongPageWithRemountKey />
    </Suspense>
  );
}
