"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useAudioPlayer } from "@/components/audio/AudioPlayerProvider";
import ReleaseGridTile from "@/components/catalog/ReleaseGridTile";
import { useAuth } from "@/context/AuthContext";
import { useAuthPrompt } from "@/context/AuthPromptContext";
import {
  API_BASE,
  fetchArtistReleasesBySlug,
  fetchArtistTracksBySlug,
  type ArtistReleasesBySlugResponse,
  type StudioCatalogTrack,
} from "@/lib/api";

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "not_found" }
  | { kind: "ready"; data: ArtistReleasesBySlugResponse };

export default function ArtistSlugPage() {
  const params = useParams();
  const router = useRouter();
  const { authReady, isAuthenticated } = useAuth();
  const { openAuthModal } = useAuthPrompt();
  const { playTrack, currentTrack, isPlaying, togglePlayback } = useAudioPlayer();
  const raw = params.slug;
  const slug = typeof raw === "string" ? raw : Array.isArray(raw) ? (raw[0] ?? "") : "";
  const [state, setState] = useState<State>({ kind: "loading" });
  const [tracks, setTracks] = useState<StudioCatalogTrack[]>([]);
  const [tracksLoading, setTracksLoading] = useState(true);

  useEffect(() => {
    if (!slug.trim()) return;
    let cancelled = false;
    void Promise.all([
      fetchArtistReleasesBySlug(slug),
      fetchArtistTracksBySlug(slug, "top"),
    ])
      .then(([releasesData, tracksData]) => {
        if (cancelled) return;
        if (releasesData.artist.slug !== slug) {
          router.replace(`/artist/${releasesData.artist.slug}`);
          return;
        }
        setState({ kind: "ready", data: releasesData });
        setTracks(tracksData.tracks);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        const msg = e instanceof Error ? e.message : "Could not load artist.";
        if (msg.toLowerCase().includes("not found")) {
          setState({ kind: "not_found" });
          return;
        }
        setState({ kind: "error", message: msg });
      })
      .finally(() => {
        if (!cancelled) {
          setTracksLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [slug, router]);

  const queuePayload = useMemo(
    () =>
      tracks
        .filter((t) => t.playable && t.audio_url)
        .map((t) => ({
          id: t.id,
          title: t.title?.trim() ? t.title : "Untitled",
          audioUrl: `${API_BASE}${t.audio_url}`,
          ...(t.cover_url ? { coverUrl: `${API_BASE}${t.cover_url}` } : {}),
        })),
    [tracks],
  );

  const activateTrack = useCallback(
    (track: StudioCatalogTrack) => {
      if (!authReady || !track.playable || !track.audio_url) return;
      if (!isAuthenticated) {
        openAuthModal();
        return;
      }
      if (currentTrack?.id === track.id) {
        void togglePlayback();
        return;
      }
      const displayTitle = track.title?.trim() ? track.title : "Untitled";
      const payload = {
        id: track.id,
        title: displayTitle,
        audioUrl: `${API_BASE}${track.audio_url}`,
        ...(track.cover_url ? { coverUrl: `${API_BASE}${track.cover_url}` } : {}),
      };
      const queueIndex = queuePayload.findIndex((row) => row.id === track.id);
      void playTrack(payload, {
        queue: queuePayload.length > 0 ? queuePayload : [payload],
        queueIndex: queueIndex >= 0 ? queueIndex : 0,
      }).catch((err) => {
        console.error("artist page track play failed", err);
      });
    },
    [
      authReady,
      currentTrack?.id,
      isAuthenticated,
      openAuthModal,
      playTrack,
      queuePayload,
      togglePlayback,
    ],
  );

  if (!slug.trim() || state.kind === "not_found") return <main className="mx-auto max-w-2xl px-4 py-12">Artist not found.</main>;
  if (state.kind === "loading") return <main className="mx-auto max-w-2xl px-4 py-12">Loading artist...</main>;
  if (state.kind === "error") return <main className="mx-auto max-w-2xl px-4 py-12">{state.message}</main>;

  const { data } = state;

  return (
    <main className="mx-auto max-w-7xl px-4 py-10">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-neutral-900 dark:text-white">
          {data.artist.name}
        </h1>
        <p className="mt-2 text-sm text-neutral-500 dark:text-neutral-400">
          /{`artist/${data.artist.slug}`}
        </p>
      </header>

      <section className="mt-8 space-y-4">
        <h2 className="text-lg font-medium text-neutral-900 dark:text-white">Releases</h2>
        {data.releases.length === 0 ? (
          <p className="text-sm text-neutral-500 dark:text-neutral-400">No published releases yet</p>
        ) : (
          <div className="grid grid-cols-3 gap-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6">
            {data.releases.map((release) => (
              <ReleaseGridTile
                key={`artist-release-${release.id}`}
                release={release}
                size="compact"
                mode="public"
              />
            ))}
          </div>
        )}
      </section>

      <section className="mt-10 space-y-4">
        <h2 className="text-lg font-medium text-neutral-900 dark:text-white">Top tracks</h2>

        {tracksLoading ? (
          <p className="text-sm text-neutral-500 dark:text-neutral-400">Loading tracks...</p>
        ) : null}

        {!tracksLoading && tracks.length === 0 ? (
          <p className="text-sm text-neutral-500 dark:text-neutral-400">No tracks yet</p>
        ) : null}

        {!tracksLoading && tracks.length > 0 ? (
          <ul className="divide-y divide-neutral-200/70 dark:divide-neutral-800">
            {tracks.map((track) => {
              const displayTitle = track.title?.trim() ? track.title : "Untitled";
              const coverSrc = track.cover_url ? `${API_BASE}${track.cover_url}` : null;
              const canPlay = Boolean(authReady && track.playable && track.audio_url);
              const isCurrent = currentTrack?.id === track.id;
              return (
                <li key={`artist-track-${track.id}`}>
                  <div
                    role="button"
                    tabIndex={0}
                    onClick={() => activateTrack(track)}
                    onKeyDown={(e) => {
                      if (e.key !== "Enter" && e.key !== " ") return;
                      e.preventDefault();
                      activateTrack(track);
                    }}
                    className="flex w-full items-center gap-3 py-2 text-left"
                  >
                    <div className="h-10 w-10 shrink-0 overflow-hidden bg-neutral-200 dark:bg-neutral-900">
                      {coverSrc ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={coverSrc} alt="" className="h-full w-full object-cover" loading="lazy" />
                      ) : null}
                    </div>

                    <div className="min-w-0 flex-1">
                      <p className="block truncate text-sm font-medium text-neutral-900 dark:text-neutral-100">
                        {displayTitle}
                      </p>
                      <p className="truncate text-xs text-neutral-500 dark:text-neutral-400">
                        {track.artist_name}
                      </p>
                    </div>

                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        activateTrack(track);
                      }}
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
                            : !isAuthenticated
                              ? `Log in to play ${displayTitle}`
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
                  </div>
                </li>
              );
            })}
          </ul>
        ) : null}
      </section>

    </main>
  );
}
