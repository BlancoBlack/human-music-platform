"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  completeOnboarding,
  fetchFirstSession,
  type DiscoveryTrack,
} from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { resolveOnboardingRoute } from "@/lib/onboarding";

const OVERLAYS = ["No algorithm manipulation", "You discover, not trends"];

export default function PlayerPage() {
  const router = useRouter();
  const { user, refreshUser } = useAuth();
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [tracks, setTracks] = useState<DiscoveryTrack[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [overlayIdx, setOverlayIdx] = useState(0);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const step = (user?.onboarding_step || "").toUpperCase();
      if (!["PREFERENCES_SET", "DISCOVERY_STARTED", "COMPLETED"].includes(step)) {
        if (!cancelled) router.replace("/onboarding");
        return;
      }
      try {
        const data = await fetchFirstSession();
        if (!cancelled) setTracks(data.tracks || []);
        const me = await refreshUser();
        const route = resolveOnboardingRoute(me);
        if (!cancelled && route) {
          router.replace(route);
          return;
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Failed to load session");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshUser, router, user?.onboarding_step]);

  useEffect(() => {
    const t = window.setInterval(() => {
      setOverlayIdx((x) => (x + 1) % OVERLAYS.length);
    }, 3000);
    return () => window.clearInterval(t);
  }, []);

  const firstTrack = useMemo(() => tracks.find((t) => t.playable && t.audio_url), [tracks]);

  async function playNow() {
    if (!firstTrack?.audio_url || !audioRef.current) return;
    audioRef.current.src = firstTrack.audio_url.startsWith("http")
      ? firstTrack.audio_url
      : `${process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000"}${firstTrack.audio_url}`;
    try {
      await audioRef.current.play();
    } catch {
      // user gesture is enough in most browsers; ignore autoplay edge cases
    }
    await completeOnboarding();
    const me = await refreshUser();
    router.replace(resolveOnboardingRoute(me) ?? "/discovery");
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-black px-4 text-white">
      <div className="w-full max-w-xl text-center">
        <p className="mb-10 text-sm text-neutral-300">{OVERLAYS[overlayIdx]}</p>
        <h1 className="text-3xl font-semibold">Ready to play</h1>
        {loading ? <p className="mt-3 text-sm text-neutral-400">Preparing your session...</p> : null}
        {error ? <p className="mt-3 text-sm text-red-400">{error}</p> : null}
        <button
          type="button"
          onClick={playNow}
          disabled={!firstTrack || loading}
          className="mt-10 w-full rounded-xl bg-[#F37D25] px-6 py-4 text-lg font-semibold text-black hover:bg-[#F7A364] disabled:opacity-50"
        >
          PLAY
        </button>
        <audio ref={audioRef} className="hidden" />
      </div>
    </main>
  );
}
