"use client";

import { useCallback, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { PlaylistModal } from "@/components/PlaylistModal";
import { useLikes } from "@/hooks/useLikes";

export function SongActions({ songId }: { songId: number }) {
  const { isAuthenticated, authReady } = useAuth();
  const { likedSongIds, loadingSongIds, like, unlike } = useLikes();
  const [playlistOpen, setPlaylistOpen] = useState(false);
  const [heartBump, setHeartBump] = useState(false);

  const liked = likedSongIds.has(songId);
  const likeBusy = loadingSongIds.has(songId);
  const disabled = !authReady || !isAuthenticated;

  const toggleLike = useCallback(() => {
    if (disabled || likeBusy) return;
    setHeartBump(true);
    window.setTimeout(() => setHeartBump(false), 200);
    if (liked) void unlike(songId);
    else void like(songId);
  }, [disabled, likeBusy, liked, like, unlike, songId]);

  return (
    <>
      <div
        className="flex shrink-0 items-center gap-0.5"
        role="group"
        aria-label="Song actions"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          disabled={disabled || likeBusy}
          title={
            disabled
              ? "Sign in to like"
              : likeBusy
                ? "Updating…"
                : liked
                  ? "Unlike"
                  : "Like"
          }
          aria-label={liked ? "Unlike" : "Like"}
          aria-pressed={liked}
          aria-busy={likeBusy}
          className={`relative rounded-full p-2 text-rose-500 transition-transform duration-150 hover:bg-rose-500/10 hover:text-rose-400 disabled:cursor-not-allowed disabled:opacity-35 dark:text-rose-400 dark:hover:bg-rose-500/15 ${
            heartBump && !likeBusy ? "scale-110" : "scale-100 active:scale-95"
          } ${likeBusy ? "opacity-70" : ""}`}
          onClick={toggleLike}
        >
          {likeBusy ? (
            <span
              className="flex h-6 w-6 items-center justify-center"
              aria-hidden
            >
              <span className="inline-block h-5 w-5 animate-spin rounded-full border-2 border-rose-400 border-t-transparent dark:border-rose-300 dark:border-t-transparent" />
            </span>
          ) : liked ? (
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="currentColor"
              className="h-6 w-6"
              aria-hidden
            >
              <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z" />
            </svg>
          ) : (
            <svg
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={1.5}
              stroke="currentColor"
              className="h-6 w-6"
              aria-hidden
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M21 8.25c0-2.485-2.099-4.5-4.688-4.5-1.935 0-3.597 1.126-4.312 2.733-.715-1.607-2.377-2.733-4.313-2.733C5.1 3.75 3 5.765 3 8.25c0 7.22 9 12 9 12s9-4.78 9-12z"
              />
            </svg>
          )}
        </button>
        <button
          type="button"
          disabled={disabled}
          title={disabled ? "Sign in to add to playlist" : "Add to playlist"}
          aria-label="Add to playlist"
          className="rounded-full p-2 text-neutral-600 transition-transform duration-150 hover:bg-neutral-200/80 hover:text-neutral-900 active:scale-95 disabled:cursor-not-allowed disabled:opacity-35 dark:text-neutral-300 dark:hover:bg-white/10 dark:hover:text-white"
          onClick={() => {
            if (disabled) return;
            setPlaylistOpen(true);
          }}
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="currentColor"
            className="h-6 w-6"
            aria-hidden
          >
            <path d="M12 5a1 1 0 011 1v5h5a1 1 0 110 2h-5v5a1 1 0 11-2 0v-5H6a1 1 0 110-2h5V6a1 1 0 011-1z" />
          </svg>
        </button>
      </div>
      <PlaylistModal
        songId={songId}
        open={playlistOpen}
        onClose={() => setPlaylistOpen(false)}
      />
    </>
  );
}
