"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useAudioPlayer } from "@/components/audio/AudioPlayerProvider";
import { SongActions } from "@/components/SongActions";
import { useAuth } from "@/context/AuthContext";
import {
  API_BASE,
  fetchDiscoveryHome,
  postDiscoveryEvent,
  type DiscoveryResponse,
  type DiscoveryTrack,
} from "@/lib/api";

function Section({
  title,
  listKey,
  requestId,
  tracks,
  emptyMessage,
  microcopy,
  variant = "default",
  emphasize = false,
}: {
  title: string;
  listKey: "play_now" | "for_you" | "explore" | "curated";
  requestId: string;
  tracks: DiscoveryTrack[];
  emptyMessage: string;
  microcopy?: string;
  variant?: "play_now" | "default";
  emphasize?: boolean;
}) {
  const headingClass =
    variant === "play_now"
      ? "mb-4 text-xl font-semibold tracking-tight"
      : "mb-3 text-lg font-semibold tracking-tight";

  if (!tracks.length) {
    return (
      <div className="mb-8">
        <h2 className={headingClass}>{title}</h2>
        {microcopy && (
          <p className="mb-2 text-sm text-neutral-400">
            {microcopy}
          </p>
        )}
        <p className="text-sm italic text-neutral-500 dark:text-neutral-400">
          {emptyMessage}
        </p>
      </div>
    );
  }

  return (
    <div
      className={`mb-8 ${emphasize ? "rounded-xl border border-emerald-400/40 bg-emerald-500/5 p-3 shadow-[0_0_0_1px_rgba(52,211,153,0.15)]" : ""}`}
    >
      <h2 className={headingClass}>{title}</h2>
      {microcopy && (
        <p className="mb-2 text-sm text-neutral-400">
          {microcopy}
        </p>
      )}
      <ul className="space-y-3" aria-label={title}>
        {tracks.map((track, index) => (
          <DiscoveryRow
            key={`${listKey}-${track.id}-${index}`}
            track={track}
            requestId={requestId}
            section={listKey}
            position={index}
            isPlayNowLead={listKey === "play_now" && index === 0}
          />
        ))}
      </ul>
    </div>
  );
}

function contextTagClass(tag: string): string {
  if (tag === "Fresh this week") {
    return "text-xs text-sky-400";
  }
  if (tag === "Trending now") {
    return "text-xs text-emerald-400";
  }
  if (tag === "Hidden gem") {
    return "text-xs italic text-neutral-500";
  }
  return "text-xs text-neutral-500";
}

function DiscoveryRow({
  track,
  requestId,
  section,
  position,
  isPlayNowLead = false,
}: {
  track: DiscoveryTrack;
  requestId: string;
  section: "play_now" | "for_you" | "explore" | "curated";
  position: number;
  isPlayNowLead?: boolean;
}) {
  const { authReady, isAuthenticated } = useAuth();
  const { playTrack, currentTrack, isPlaying, togglePlayback, isActivationClickSuppressed } =
    useAudioPlayer();

  const coverSrc =
    track.cover_url != null ? `${API_BASE}${track.cover_url}` : null;
  const displayTitle = track.title?.trim() ? track.title : "Untitled";
  const canAttemptPlay = Boolean(track.playable && track.audio_url && authReady);
  const canPlay = Boolean(canAttemptPlay && isAuthenticated);
  const isCurrent = currentTrack?.id === track.id;

  const emitPlayTelemetry = useCallback(
    (allowedToPlay: boolean, blockedReason: "unauth" | "not_playable" | null) => {
      void postDiscoveryEvent({
        event_type: "play_click",
        request_id: requestId,
        song_id: track.id,
        section,
        position,
        auth_state: isAuthenticated ? "authenticated" : "anonymous",
        allowed_to_play: allowedToPlay,
        blocked_reason: blockedReason,
        ranking_version: "v1",
      }).catch((e) => {
        console.error("discovery telemetry failed", e);
      });
    },
    [isAuthenticated, position, requestId, section, track.id],
  );

  const handleActivate = useCallback(() => {
    const blockedReason = !isAuthenticated ? "unauth" : !track.playable || !track.audio_url ? "not_playable" : null;
    emitPlayTelemetry(canPlay, blockedReason);
    if (!canAttemptPlay || !canPlay || !track.audio_url) return;
    if (currentTrack?.id === track.id) {
      void togglePlayback();
      return;
    }
    const payload = {
      id: track.id,
      title: displayTitle,
      audioUrl: `${API_BASE}${track.audio_url}`,
      ...(track.cover_url != null
        ? { coverUrl: `${API_BASE}${track.cover_url}` }
        : {}),
    };
    void playTrack(payload, {
      queue: [payload],
      queueIndex: 0,
      discoveryContext: { request_id: requestId, section, position },
    }).catch(
      (e) => {
        console.error("discovery play failed", e);
      },
    );
  }, [
    canAttemptPlay,
    canPlay,
    requestId,
    section,
    position,
    track.audio_url,
    track.playable,
    track.cover_url,
    track.id,
    displayTitle,
    playTrack,
    currentTrack?.id,
    togglePlayback,
    emitPlayTelemetry,
    isAuthenticated,
  ]);

  const handlePlayButton = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      if (!canAttemptPlay) return;
      if (isCurrent && canPlay) {
        void togglePlayback();
        return;
      }
      handleActivate();
    },
    [canAttemptPlay, canPlay, isCurrent, togglePlayback, handleActivate],
  );

  const rowClass = canAttemptPlay
    ? `rounded-xl border border-white/10 bg-white/5 p-3 shadow-sm transition duration-150 hover:border-white/20 hover:bg-white/[0.08] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-neutral-400 dark:focus-visible:ring-neutral-500 ${
        isCurrent
          ? "cursor-pointer ring-2 ring-emerald-500/50 dark:ring-emerald-400/40"
          : "cursor-pointer"
      } ${
        isPlayNowLead ? "border-emerald-400/40 shadow-[0_0_0_1px_rgba(52,211,153,0.2)]" : ""
      }`
    : "rounded-xl border border-white/10 bg-white/5 p-3 opacity-50";

  return (
    <li>
      <div
        className={rowClass}
        role={canAttemptPlay ? "button" : undefined}
        tabIndex={canAttemptPlay ? 0 : undefined}
        onClick={
          canAttemptPlay
            ? () => {
                if (isActivationClickSuppressed()) return;
                handleActivate();
              }
            : undefined
        }
        onKeyDown={
          canAttemptPlay
            ? (e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  handleActivate();
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
              <div className="flex h-full w-full items-center justify-center text-xs text-neutral-500 dark:text-neutral-500">
                No cover
              </div>
            )}
          </div>
          <div className="min-w-0 flex-1">
            <p className="font-medium text-neutral-900 dark:text-neutral-100">
              {displayTitle}
            </p>
            <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-400">
              {track.artist_name?.trim() || "Unknown artist"}
            </p>
            {track.context_tag && (
              <span className={contextTagClass(track.context_tag)}>
                {track.context_tag}
              </span>
            )}
            {!canAttemptPlay && (
              <p className="mt-2 text-xs font-medium text-neutral-500 dark:text-neutral-500">
                Not playable
              </p>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-1 self-center sm:gap-2">
            <SongActions songId={track.id} />
            {canAttemptPlay ? (
              <button
                type="button"
                className="flex h-10 w-10 cursor-pointer items-center justify-center rounded-full bg-neutral-900 text-white shadow-sm transition hover:scale-105 hover:bg-neutral-800 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-white"
                aria-label={
                  isCurrent && isPlaying
                    ? `Pause ${displayTitle}`
                    : `Play ${displayTitle}`
                }
                onClick={handlePlayButton}
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
            ) : (
              <button
                type="button"
                disabled
                className="flex h-10 w-10 cursor-not-allowed items-center justify-center rounded-full border border-neutral-300 bg-neutral-100 text-neutral-400 dark:border-neutral-600 dark:bg-neutral-800 dark:text-neutral-600"
                aria-label={`Not playable: ${displayTitle}`}
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 24 24"
                  fill="currentColor"
                  className="h-5 w-5 pl-0.5 opacity-50"
                  aria-hidden
                >
                  <path d="M8 5v14l11-7L8 5z" />
                </svg>
              </button>
            )}
          </div>
        </div>
      </div>
    </li>
  );
}

export default function DiscoveryPage() {
  const searchParams = useSearchParams();
  const fromOnboarding = useMemo(
    () => searchParams.get("from") === "onboarding",
    [searchParams],
  );
  const [data, setData] = useState<DiscoveryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showReadyBanner, setShowReadyBanner] = useState(fromOnboarding);

  useEffect(() => {
    if (!fromOnboarding || !showReadyBanner) return;
    const timeoutId = window.setTimeout(() => {
      setShowReadyBanner(false);
    }, 4500);
    return () => window.clearTimeout(timeoutId);
  }, [fromOnboarding, showReadyBanner]);

  useEffect(() => {
    let cancelled = false;
    void fetchDiscoveryHome()
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setData(null);
          setError(
            e instanceof Error ? e.message : "Could not load discovery.",
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="mx-auto max-w-2xl px-4 py-10">
      {/* EXPRESSION_LAYER: reserved for future illustration/motion integration */}
      <h1 className="mb-2 text-2xl font-semibold tracking-tight">Discovery</h1>
      <p className="mb-6 text-sm text-neutral-400">
        Music picked for you — based on your activity and platform trends
      </p>

      {showReadyBanner && (
        <div
          className="mb-5 rounded-lg border border-emerald-300/40 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-100"
          role="status"
        >
          <p className="font-medium">Your feed is ready.</p>
          <p className="text-emerald-200/90">Personalized for you. Press play whenever you want.</p>
        </div>
      )}

      {loading && (
        <p className="text-sm text-neutral-500 dark:text-neutral-400">
          Loading…
        </p>
      )}

      {error && (
        <p
          className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-100"
          role="alert"
        >
          {error}
        </p>
      )}

      {!loading && !error && data && (
        <>
          <Section
            title="Play now"
            listKey="play_now"
            requestId={data.request_id}
            tracks={data.play_now}
            variant="play_now"
            emptyMessage="Nothing queued yet"
            microcopy={data.section_microcopy?.play_now}
            emphasize={fromOnboarding}
          />
          <Section
            title="For you"
            listKey="for_you"
            requestId={data.request_id}
            tracks={data.for_you}
            emptyMessage="We're still learning your taste"
            microcopy={data.section_microcopy?.for_you}
          />
          <Section
            title="Explore"
            listKey="explore"
            requestId={data.request_id}
            tracks={data.explore}
            emptyMessage="Not enough signal yet — keep listening"
            microcopy={data.section_microcopy?.explore}
          />
          <Section
            title="Curated"
            listKey="curated"
            requestId={data.request_id}
            tracks={data.curated}
            emptyMessage="Curated picks coming soon"
            microcopy={data.section_microcopy?.curated}
          />
        </>
      )}
    </main>
  );
}
