"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MutableRefObject,
} from "react";
import {
  postCheckpoint,
  postFinalizeWithRetry,
  postStartSession,
} from "@/lib/listening";

export type PlayableTrack = {
  id: number;
  title: string;
  audioUrl: string;
  coverUrl?: string;
};

export type PlayTrackOptions = {
  /** Full ordered queue (e.g. playable catalog rows). Defaults to `[track]`. */
  queue?: PlayableTrack[];
  /** Index of `track` in `queue`. Defaults to matching `track.id` in `queue`. */
  queueIndex?: number;
};

type AudioPlayerContextValue = {
  currentTrack: PlayableTrack | null;
  isPlaying: boolean;
  /** True while start-session + decode/play() are in flight after user chose a track */
  isBuffering: boolean;
  /** Playback position in seconds (from the audio element timeupdate event) */
  currentTime: number;
  /** Media duration in seconds when known (from loadedmetadata) */
  duration: number;
  /** Active navigation queue (same order as when playback started from catalog). */
  queue: PlayableTrack[];
  /** Index of `currentTrack` in `queue`, or 0 if queue is empty. */
  currentIndex: number;
  playTrack: (track: PlayableTrack, opts?: PlayTrackOptions) => Promise<void>;
  nextTrack: () => Promise<void>;
  prevTrack: () => Promise<void>;
  pause: () => void;
  seekTo: (seconds: number) => void;
  togglePlayback: () => Promise<void>;
};

const AudioPlayerContext = createContext<AudioPlayerContextValue | null>(null);

/** Next index in queue with a usable `audioUrl`, or -1. */
function findNextPlayableQueueIndex(
  queue: PlayableTrack[],
  currentIndex: number,
): number {
  for (let i = currentIndex + 1; i < queue.length; i++) {
    const t = queue[i];
    if (t?.audioUrl) return i;
  }
  return -1;
}

function stopEngageClock(
  engageClockStartRef: MutableRefObject<number | null>,
  engagedMsRef: MutableRefObject<number>,
) {
  if (engageClockStartRef.current !== null) {
    engagedMsRef.current += performance.now() - engageClockStartRef.current;
    engageClockStartRef.current = null;
  }
}

function startEngageClock(engageClockStartRef: MutableRefObject<number | null>) {
  if (engageClockStartRef.current === null) {
    engageClockStartRef.current = performance.now();
  }
}

export function AudioPlayerProvider({ children }: { children: React.ReactNode }) {
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const sessionIdRef = useRef<number | null>(null);
  const songIdRef = useRef<number | null>(null);
  const nextSequenceRef = useRef(0);
  const engagedMsRef = useRef(0);
  const engageClockStartRef = useRef<number | null>(null);
  const finalizedSessionsRef = useRef<Set<number>>(new Set());
  const queueRef = useRef<PlayableTrack[]>([]);
  const currentIndexRef = useRef(0);
  const playTrackRef = useRef<
    (track: PlayableTrack, opts?: PlayTrackOptions) => Promise<void>
  >(async () => {});

  const [currentTrack, setCurrentTrack] = useState<PlayableTrack | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isBuffering, setIsBuffering] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [queue, setQueue] = useState<PlayableTrack[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);

  /* eslint-disable react-hooks/set-state-in-effect -- batch reset when track cleared */
  useEffect(() => {
    if (currentTrack == null) {
      setCurrentTime(0);
      setDuration(0);
      setQueue([]);
      setCurrentIndex(0);
    }
  }, [currentTrack]);
  /* eslint-enable react-hooks/set-state-in-effect */

  const finalizeSession = useCallback(
    async (
      sessionId: number,
      songId: number,
      durationSeconds: number,
      opts?: { keepalive?: boolean },
    ) => {
      if (finalizedSessionsRef.current.has(sessionId)) return;
      if (durationSeconds <= 0) return;

      const idempotency_key = `finalize-${sessionId}`;
      await postFinalizeWithRetry(
        {
          song_id: songId,
          duration: durationSeconds,
          session_id: sessionId,
          idempotency_key,
        },
        { keepalive: opts?.keepalive === true },
      );
      finalizedSessionsRef.current.add(sessionId);
    },
    [],
  );

  const finalizeCurrentIfNeeded = useCallback(
    async (opts?: { keepalive?: boolean }) => {
      stopEngageClock(engageClockStartRef, engagedMsRef);
      const sid = sessionIdRef.current;
      const gid = songIdRef.current;
      const sec = Math.floor(engagedMsRef.current / 1000);
      sessionIdRef.current = null;
      songIdRef.current = null;
      nextSequenceRef.current = 0;
      engagedMsRef.current = 0;

      if (sid != null && gid != null && sec > 0) {
        try {
          await finalizeSession(sid, gid, sec, {
            keepalive: opts?.keepalive === true,
          });
        } catch (e) {
          console.error("finalize failed", e);
        }
      }
    },
    [finalizeSession],
  );

  const sendCheckpoint = useCallback(async () => {
    const el = audioRef.current;
    const sid = sessionIdRef.current;
    const gid = songIdRef.current;
    if (!el || el.paused || el.ended || sid == null || gid == null) return;

    const sequence = nextSequenceRef.current;
    const position_seconds = Math.floor(el.currentTime);

    const body = {
      session_id: sid,
      song_id: gid,
      sequence,
      position_seconds,
    };

    let res: Response;
    try {
      res = await postCheckpoint(body);
      let r429 = 0;
      while (res.status === 429 && r429 < 2) {
        await new Promise((r) => setTimeout(r, 1500));
        r429 += 1;
        res = await postCheckpoint(body);
      }
    } catch (e) {
      console.error("checkpoint network error", e);
      return;
    }

    if (res.status === 410) {
      stopEngageClock(engageClockStartRef, engagedMsRef);
      const expiredSid = sid;
      const expiredGid = gid;
      const sec = Math.floor(engagedMsRef.current / 1000);
      sessionIdRef.current = null;
      nextSequenceRef.current = 0;

      if (sec > 0) {
        try {
          await finalizeSession(expiredSid, expiredGid, sec);
        } catch (e) {
          console.error(
            "[ingestion] finalize after session_expired (410) failed after retries — stopping playback (listen data not confirmed)",
            e,
          );
          el.pause();
          el.removeAttribute("src");
          el.load();
          engagedMsRef.current = 0;
          songIdRef.current = null;
          setCurrentTrack(null);
          setIsPlaying(false);
          setIsBuffering(false);
          return;
        }
      }
      engagedMsRef.current = 0;

      try {
        const { session_id } = await postStartSession(expiredGid);
        sessionIdRef.current = session_id;
        songIdRef.current = expiredGid;
        nextSequenceRef.current = 0;
        if (el && !el.paused && !el.ended) {
          startEngageClock(engageClockStartRef);
        }
      } catch (e) {
        console.error("renew session after 410 failed", e);
        songIdRef.current = null;
      }
      return;
    }

    if (res.ok) {
      nextSequenceRef.current = sequence + 1;
      return;
    }

    const text = await res.text().catch(() => "");
    console.warn("checkpoint rejected", res.status, text);
  }, [finalizeSession]);

  useEffect(() => {
    if (!currentTrack) return;
    const id = window.setInterval(() => {
      void sendCheckpoint();
    }, 30_000);
    return () => window.clearInterval(id);
  }, [currentTrack?.id, sendCheckpoint]); // eslint-disable-line react-hooks/exhaustive-deps -- interval when track id changes only

  useEffect(() => {
    const onUnloadLifecycle = () => {
      void finalizeCurrentIfNeeded({ keepalive: true });
    };
    window.addEventListener("pagehide", onUnloadLifecycle);
    window.addEventListener("beforeunload", onUnloadLifecycle);
    return () => {
      window.removeEventListener("pagehide", onUnloadLifecycle);
      window.removeEventListener("beforeunload", onUnloadLifecycle);
    };
  }, [finalizeCurrentIfNeeded]);

  const playTrack = useCallback(
    async (track: PlayableTrack, opts?: PlayTrackOptions) => {
      if (!track.audioUrl) {
        console.warn("playTrack: missing audioUrl");
        return;
      }

      const el = audioRef.current;
      if (!el) return;

      const q = opts?.queue ?? [track];
      let idx =
        opts?.queueIndex ??
        q.findIndex((t) => t.id === track.id);
      if (idx < 0) idx = 0;

      await finalizeCurrentIfNeeded();

      setQueue(q);
      setCurrentIndex(idx);
      setCurrentTrack(track);
      setCurrentTime(0);
      setDuration(0);
      setIsBuffering(true);

      const songId = track.id;
      let session_id: number;
      try {
        const started = await postStartSession(songId);
        session_id = started.session_id;
      } catch (e) {
        setCurrentTrack(null);
        setIsBuffering(false);
        console.error("start-session failed", e);
        throw e;
      }

      sessionIdRef.current = session_id;
      songIdRef.current = songId;
      nextSequenceRef.current = 0;
      engagedMsRef.current = 0;
      engageClockStartRef.current = null;

      el.src = track.audioUrl;
      el.load();
      try {
        await el.play();
      } catch {
        try {
          await el.play();
        } catch (secondErr) {
          sessionIdRef.current = null;
          songIdRef.current = null;
          nextSequenceRef.current = 0;
          engageClockStartRef.current = null;
          engagedMsRef.current = 0;
          setCurrentTrack(null);
          setIsBuffering(false);
          console.error(
            "[ingestion] play() failed after start-session (session abandoned; no listening event)",
            secondErr,
          );
          throw secondErr;
        }
      }
      setIsBuffering(false);
    },
    [finalizeCurrentIfNeeded],
  );

  useEffect(() => {
    queueRef.current = queue;
    currentIndexRef.current = currentIndex;
    playTrackRef.current = playTrack;
  }, [queue, currentIndex, playTrack]);

  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;

    const onPlay = () => {
      startEngageClock(engageClockStartRef);
      setIsPlaying(true);
    };
    const onPause = () => {
      stopEngageClock(engageClockStartRef, engagedMsRef);
      setIsPlaying(false);
    };
    const onEnded = async () => {
      stopEngageClock(engageClockStartRef, engagedMsRef);
      setIsPlaying(false);
      setIsBuffering(false);
      const sid = sessionIdRef.current;
      const gid = songIdRef.current;
      const sec = Math.floor(engagedMsRef.current / 1000);
      sessionIdRef.current = null;
      songIdRef.current = null;
      nextSequenceRef.current = 0;
      engagedMsRef.current = 0;
      if (sid != null && gid != null && sec > 0) {
        try {
          await finalizeSession(sid, gid, sec);
        } catch (e) {
          console.error("finalize on ended failed", e);
        }
      }

      const q = queueRef.current;
      const idx = currentIndexRef.current;
      const nextIdx = findNextPlayableQueueIndex(q, idx);
      if (nextIdx >= 0) {
        const next = q[nextIdx];
        try {
          await playTrackRef.current(next, { queue: q, queueIndex: nextIdx });
        } catch (e) {
          console.error("autoplay next track failed", e);
        }
      }
    };

    const onTimeUpdate = () => {
      const t = el.currentTime;
      setCurrentTime(Number.isFinite(t) ? t : 0);
    };
    const onLoadedMetadata = () => {
      const d = el.duration;
      setDuration(Number.isFinite(d) && d > 0 ? d : 0);
      const t = el.currentTime;
      setCurrentTime(Number.isFinite(t) ? t : 0);
    };

    el.addEventListener("play", onPlay);
    el.addEventListener("pause", onPause);
    el.addEventListener("ended", onEnded);
    el.addEventListener("timeupdate", onTimeUpdate);
    el.addEventListener("loadedmetadata", onLoadedMetadata);
    return () => {
      el.removeEventListener("play", onPlay);
      el.removeEventListener("pause", onPause);
      el.removeEventListener("ended", onEnded);
      el.removeEventListener("timeupdate", onTimeUpdate);
      el.removeEventListener("loadedmetadata", onLoadedMetadata);
    };
  }, [finalizeSession]);

  const pause = useCallback(() => {
    audioRef.current?.pause();
  }, []);

  const seekTo = useCallback((seconds: number) => {
    const el = audioRef.current;
    if (!el) return;
    const d = el.duration;
    if (!Number.isFinite(d) || d <= 0) return;
    el.currentTime = Math.min(d, Math.max(0, seconds));
  }, []);

  const togglePlayback = useCallback(async () => {
    const el = audioRef.current;
    if (!el || !currentTrack || isBuffering) return;
    if (!el.src) return;
    if (el.ended) {
      await playTrack(currentTrack, { queue, queueIndex: currentIndex });
      return;
    }
    if (el.paused) {
      try {
        await el.play();
      } catch (e) {
        console.error("resume failed", e);
      }
    } else {
      el.pause();
    }
  }, [currentTrack, currentIndex, isBuffering, playTrack, queue]);

  const nextTrack = useCallback(async () => {
    if (currentIndex >= queue.length - 1) return;
    const next = queue[currentIndex + 1];
    if (!next?.audioUrl) return;
    try {
      await playTrack(next, { queue, queueIndex: currentIndex + 1 });
    } catch (e) {
      console.error("nextTrack failed", e);
    }
  }, [queue, currentIndex, playTrack]);

  const prevTrack = useCallback(async () => {
    if (currentIndex <= 0) return;
    const prev = queue[currentIndex - 1];
    if (!prev?.audioUrl) return;
    try {
      await playTrack(prev, { queue, queueIndex: currentIndex - 1 });
    } catch (e) {
      console.error("prevTrack failed", e);
    }
  }, [queue, currentIndex, playTrack]);

  const value = useMemo(
    () => ({
      currentTrack,
      isPlaying,
      isBuffering,
      currentTime,
      duration,
      queue,
      currentIndex,
      playTrack,
      nextTrack,
      prevTrack,
      pause,
      seekTo,
      togglePlayback,
    }),
    [
      currentTrack,
      isPlaying,
      isBuffering,
      currentTime,
      duration,
      queue,
      currentIndex,
      playTrack,
      nextTrack,
      prevTrack,
      pause,
      seekTo,
      togglePlayback,
    ],
  );

  return (
    <AudioPlayerContext.Provider value={value}>
      <audio
        ref={audioRef}
        className="sr-only"
        preload="metadata"
        aria-hidden
        playsInline
      />
      {children}
    </AudioPlayerContext.Provider>
  );
}

export function useAudioPlayer(): AudioPlayerContextValue {
  const ctx = useContext(AudioPlayerContext);
  if (!ctx) {
    throw new Error("useAudioPlayer must be used within AudioPlayerProvider");
  }
  return ctx;
}
