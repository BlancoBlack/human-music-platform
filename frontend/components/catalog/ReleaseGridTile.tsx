"use client";

import { useRouter } from "next/navigation";
import type { MouseEvent } from "react";
import { useCallback } from "react";
import { useAudioPlayer } from "@/components/audio/AudioPlayerProvider";
import { useAuth } from "@/context/AuthContext";
import { useAuthPrompt } from "@/context/AuthPromptContext";
import { API_BASE, type StudioCatalogRelease } from "@/lib/api";

type ReleaseGridTileProps = {
  release: StudioCatalogRelease;
  size?: "default" | "compact";
  mode?: "studio" | "public";
};

export default function ReleaseGridTile({
  release,
  size = "default",
  mode = "studio",
}: ReleaseGridTileProps) {
  const router = useRouter();
  const { authReady, isAuthenticated } = useAuth();
  const { openAuthModal } = useAuthPrompt();
  const { playTrack, currentTrack, isPlaying, togglePlayback } = useAudioPlayer();
  const compact = size === "compact";
  const showEdit = mode === "studio";

  const cover = release.cover_url ? `${API_BASE}${release.cover_url}` : null;
  const track = release.first_track;
  const displayTitle = track?.title?.trim() ? track.title : "Untitled";
  const hasPlayableTrack = Boolean(track?.playable && track.audio_url);
  const canInteractWithPlay = Boolean(authReady && hasPlayableTrack);
  const isCurrent = track != null && currentTrack?.id === track.id;

  const openRelease = useCallback(() => {
    router.push(`/album/${release.slug}`);
  }, [release.slug, router]);

  const handleEdit = useCallback(
    (e: MouseEvent<HTMLButtonElement>) => {
      e.stopPropagation();
      router.push(`/studio/release/${release.id}/edit`);
    },
    [release.id, router],
  );

  const handlePlay = useCallback(
    (e: MouseEvent<HTMLButtonElement>) => {
      e.stopPropagation();
      if (!track || !authReady || !track.playable || !track.audio_url) return;
      if (!isAuthenticated) {
        if (mode === "public") {
          openAuthModal();
        }
        return;
      }
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
      void playTrack(payload, { queue: [payload], queueIndex: 0 }).catch((err) => {
        console.error("release tile play failed", err);
      });
    },
    [
      authReady,
      currentTrack?.id,
      displayTitle,
      isAuthenticated,
      mode,
      openAuthModal,
      playTrack,
      togglePlayback,
      track,
    ],
  );

  return (
    <div className="group relative aspect-square overflow-hidden bg-neutral-200 dark:bg-neutral-900">
        <div className="absolute inset-0 z-0">
          {cover ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={cover}
              alt=""
              loading={compact ? "lazy" : undefined}
              className="h-full w-full object-cover transition duration-300 group-hover:scale-105"
            />
          ) : (
            <div
              className={
                compact
                  ? "flex h-full w-full items-center justify-center text-[10px] text-neutral-500 dark:text-neutral-500"
                  : "flex h-full w-full items-center justify-center text-xs text-neutral-500 dark:text-neutral-500"
              }
            >
              Add cover
            </div>
          )}
        </div>

        <div
          role="link"
          tabIndex={0}
          className="absolute inset-0 z-[1] cursor-pointer"
          onClick={openRelease}
          onKeyDown={(e) => {
            if (e.key !== "Enter" && e.key !== " ") return;
            e.preventDefault();
            openRelease();
          }}
          aria-label={`Open ${release.title}`}
        />

        <div className="pointer-events-none absolute inset-0 z-[2] bg-black/0 transition duration-300 group-hover:bg-black/45" />

        <div className="pointer-events-none absolute inset-0 z-[3] flex items-center justify-center px-1.5 opacity-0 transition duration-300 group-hover:opacity-100 sm:px-2">
          <p
            className={
              compact
                ? "line-clamp-2 text-center text-xs font-medium text-white drop-shadow"
                : "line-clamp-2 text-center text-sm font-medium text-white drop-shadow"
            }
          >
            {release.title}
          </p>
        </div>

        {showEdit ? (
          <button
            type="button"
            className={
              compact
                ? "absolute right-1 top-1 z-20 rounded px-1 py-0.5 text-[10px] text-white opacity-0 transition-opacity duration-150 hover:underline group-hover:opacity-100 sm:right-1.5 sm:top-1.5 sm:text-xs"
                : "absolute right-2 top-2 z-20 rounded px-1.5 py-0.5 text-xs text-white opacity-0 transition-opacity duration-150 hover:underline group-hover:opacity-100"
            }
            onClick={handleEdit}
          >
            Edit
          </button>
        ) : null}

        <button
          type="button"
          disabled={!canInteractWithPlay}
          onClick={handlePlay}
          className={
            canInteractWithPlay
              ? compact
                ? "absolute bottom-1 right-1 z-20 flex h-8 w-8 items-center justify-center rounded-full bg-white text-black opacity-0 shadow-md transition duration-150 group-hover:opacity-100 hover:bg-neutral-100 sm:bottom-1.5 sm:right-1.5"
                : "absolute bottom-2 right-2 z-20 flex h-10 w-10 items-center justify-center rounded-full bg-white text-black opacity-0 shadow-md transition duration-150 group-hover:opacity-100 hover:bg-neutral-100"
              : compact
                ? "absolute bottom-1 right-1 z-20 flex h-8 w-8 cursor-not-allowed items-center justify-center rounded-full bg-white/50 text-black/40 opacity-0 transition duration-150 group-hover:opacity-100 sm:bottom-1.5 sm:right-1.5"
                : "absolute bottom-2 right-2 z-20 flex h-10 w-10 cursor-not-allowed items-center justify-center rounded-full bg-white/50 text-black/40 opacity-0 transition duration-150 group-hover:opacity-100"
          }
          aria-label={
            !canInteractWithPlay
              ? track
                ? `Not playable: ${release.title}`
                : `No playable track: ${release.title}`
              : !isAuthenticated && mode === "public"
                ? `Log in to play ${displayTitle}`
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
              className={compact ? "h-4 w-4" : "h-5 w-5"}
              aria-hidden
            >
              <path d="M6 5h4v14H6V5zm8 0h4v14h-4V5z" />
            </svg>
          ) : (
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="currentColor"
              className={compact ? "h-4 w-4 pl-0.5" : "h-5 w-5 pl-0.5"}
              aria-hidden
            >
              <path d="M8 5v14l11-7L8 5z" />
            </svg>
          )}
        </button>
      </div>
  );
}
