"use client";

import type { MouseEvent } from "react";
import { useAudioPlayer } from "@/components/audio/AudioPlayerProvider";

export function GlobalPlayerBar() {
  const {
    currentTrack,
    isPlaying,
    isBuffering,
    currentTime,
    duration,
    queue,
    currentIndex,
    prevTrack,
    togglePlayback,
    nextTrack,
    seekTo,
  } = useAudioPlayer();

  if (!currentTrack) {
    return null;
  }

  const progressPct =
    duration > 0
      ? Math.min(100, Math.max(0, (currentTime / duration) * 100))
      : 0;

  const statusLine = isBuffering
    ? "Starting playback…"
    : isPlaying
      ? "Playing"
      : "Paused";

  const canPrev = currentIndex > 0 && queue.length > 0;
  const canNext = currentIndex < queue.length - 1 && queue.length > 0;

  const handleProgressClick = (e: MouseEvent<HTMLDivElement>) => {
    if (duration <= 0) return;
    const rect = e.currentTarget.getBoundingClientRect();
    if (rect.width <= 0) return;
    const x = e.clientX - rect.left;
    const ratio = Math.min(1, Math.max(0, x / rect.width));
    const targetTime = ratio * duration;
    seekTo(targetTime);
  };

  return (
    <div
      className="fixed inset-x-0 bottom-0 z-50 border-t border-neutral-200 bg-white/95 px-4 py-3 shadow-[0_-4px_24px_rgba(0,0,0,0.06)] backdrop-blur-md dark:border-neutral-800 dark:bg-neutral-950/95"
      role="region"
      aria-label="Now playing"
    >
      <div className="mx-auto max-w-3xl">
        <div className="flex items-center gap-3">
          <div className="relative h-12 w-12 shrink-0 overflow-hidden rounded bg-neutral-200 dark:bg-neutral-800">
            {currentTrack.coverUrl ? (
              // eslint-disable-next-line @next/next/no-img-element -- API absolute URL
              <img
                src={currentTrack.coverUrl}
                alt=""
                className="h-12 w-12 object-cover"
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
                  className="h-7 w-7 opacity-90"
                >
                  <path d="M12 3v9.55A4 4 0 1 0 14 17V7h4V3h-6z" />
                </svg>
              </div>
            )}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-neutral-900 dark:text-neutral-100">
              {currentTrack.title}
            </p>
            <p className="mt-0.5 flex items-center gap-2 truncate text-xs text-neutral-500 dark:text-neutral-400">
              {isBuffering && (
                <span
                  className="inline-block h-3.5 w-3.5 shrink-0 animate-spin rounded-full border-2 border-neutral-300 border-t-neutral-700 dark:border-neutral-600 dark:border-t-neutral-200"
                  aria-hidden
                />
              )}
              <span className="truncate">{statusLine}</span>
            </p>
            <div
              className="progress-bar mt-2 h-1 w-full cursor-pointer overflow-hidden rounded-full bg-neutral-200 dark:bg-neutral-700"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(progressPct)}
              aria-label="Playback position"
              onClick={handleProgressClick}
            >
              <div
                className="h-full rounded-full bg-neutral-900 transition-[width] duration-150 ease-linear dark:bg-neutral-100"
                style={{ width: `${progressPct}%` }}
              />
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1 sm:gap-2 self-center">
            <button
              type="button"
              disabled={isBuffering || !canPrev}
              onClick={() => void prevTrack()}
              className="flex h-10 w-10 items-center justify-center rounded-full text-neutral-700 transition hover:bg-neutral-100 disabled:cursor-not-allowed disabled:opacity-30 dark:text-neutral-200 dark:hover:bg-neutral-800 dark:disabled:opacity-30"
              aria-label="Previous track"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                fill="currentColor"
                className="h-6 w-6"
                aria-hidden
              >
                <path d="M6 6h2v12H6V6zm3.5 6 8.5 6V6l-8.5 6z" />
              </svg>
            </button>
            <button
              type="button"
              disabled={isBuffering}
              onClick={() => void togglePlayback()}
              className="flex h-10 w-10 items-center justify-center rounded-full bg-neutral-900 text-white transition hover:bg-neutral-800 disabled:cursor-not-allowed disabled:opacity-40 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-white dark:disabled:opacity-40"
              aria-label={isPlaying ? "Pause" : "Play"}
              aria-busy={isBuffering}
            >
              {isPlaying ? (
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
            <button
              type="button"
              disabled={isBuffering || !canNext}
              onClick={() => void nextTrack()}
              className="flex h-10 w-10 items-center justify-center rounded-full text-neutral-700 transition hover:bg-neutral-100 disabled:cursor-not-allowed disabled:opacity-30 dark:text-neutral-200 dark:hover:bg-neutral-800 dark:disabled:opacity-30"
              aria-label="Next track"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                fill="currentColor"
                className="h-6 w-6"
                aria-hidden
              >
                <path d="M16 18h2V6h-2v12zM6 18l8.5-6L6 6v12z" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
