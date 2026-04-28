"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { API_BASE, ApiNotFoundError, fetchTrackBySlug, type TrackBySlugResponse } from "@/lib/api";
import { useAudioPlayer } from "@/components/audio/AudioPlayerProvider";

type LoadState =
  | { kind: "loading" }
  | { kind: "not_found" }
  | { kind: "error"; message: string }
  | { kind: "ready"; track: TrackBySlugResponse };

export default function TrackSlugPage() {
  const params = useParams();
  const router = useRouter();
  const raw = params.slug;
  const slug = typeof raw === "string" ? raw : Array.isArray(raw) ? (raw[0] ?? "") : "";
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [playError, setPlayError] = useState<string | null>(null);
  const { playTrack, currentTrack, isPlaying, togglePlayback } = useAudioPlayer();

  useEffect(() => {
    if (!slug.trim()) return;
    let cancelled = false;
    void fetchTrackBySlug(slug)
      .then((track) => {
        if (cancelled) return;
        if (track.slug !== slug) {
          router.replace(`/track/${track.slug}`);
          return;
        }
        setState({ kind: "ready", track });
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        if (e instanceof ApiNotFoundError) {
          setState({ kind: "not_found" });
          return;
        }
        setState({ kind: "error", message: e instanceof Error ? e.message : "Could not load track." });
      });
    return () => {
      cancelled = true;
    };
  }, [slug, router]);

  const playable = useMemo(
    () => state.kind === "ready" && state.track.has_master_audio && state.track.upload_status === "ready",
    [state],
  );

  const onPlay = () => {
    if (state.kind !== "ready" || !playable || !state.track.audio_url) return;
    const track = state.track;
    if (currentTrack?.id === track.id) {
      void togglePlayback();
      return;
    }
    setPlayError(null);
    void playTrack({
      id: track.id,
      title: track.title?.trim() ? track.title : "Untitled",
      audioUrl: `${API_BASE}${track.audio_url}`,
      ...(track.cover_url ? { coverUrl: `${API_BASE}${track.cover_url}` } : {}),
    }).catch((e) => {
      setPlayError(e instanceof Error ? e.message : "Could not start playback.");
    });
  };

  if (!slug.trim() || state.kind === "not_found") {
    return <main className="mx-auto max-w-xl px-4 py-12 text-sm">Track not found.</main>;
  }
  if (state.kind === "loading") {
    return <main className="mx-auto max-w-xl px-4 py-12 text-sm text-neutral-500">Loading track...</main>;
  }
  if (state.kind === "error") {
    return <main className="mx-auto max-w-xl px-4 py-12 text-sm">{state.message}</main>;
  }

  const track = state.track;
  const isCurrent = currentTrack?.id === track.id;
  const coverSrc = track.cover_url ? `${API_BASE}${track.cover_url}` : null;

  return (
    <main className="mx-auto max-w-xl px-4 py-10">
      <div className="mb-6 text-sm text-neutral-600 dark:text-neutral-400">
        <Link href={`/artist/${track.artist.slug}`} className="underline">
          {track.artist.name}
        </Link>
        {track.album ? (
          <>
            <span> {" > "} </span>
            <Link href={`/album/${track.album.slug}`} className="underline">
              {track.album.title}
            </Link>
          </>
        ) : null}
      </div>
      <h1 className="text-2xl font-semibold">{track.title || "Untitled"}</h1>
      <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-400">{track.artist.name}</p>
      {coverSrc ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={coverSrc} alt="" className="mt-6 w-full rounded-xl border border-neutral-200 dark:border-neutral-800" />
      ) : null}
      {playError ? <p className="mt-4 text-sm text-amber-600">{playError}</p> : null}
      <button
        type="button"
        disabled={!playable}
        onClick={onPlay}
        className="mt-6 w-full rounded-xl bg-neutral-900 px-4 py-3 text-sm font-medium text-white disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900"
      >
        {isCurrent && isPlaying ? "Pause" : "Play"}
      </button>
    </main>
  );
}
