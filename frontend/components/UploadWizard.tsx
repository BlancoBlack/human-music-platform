"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  API_BASE,
  apiFetch,
  fetchArtist,
  fetchSong,
  parseErrorPayload,
  searchArtists,
  type ArtistPublic,
  type SongDetail,
} from "@/lib/api";

const STORAGE_KEY = "uploadWizardSongId";

const CREDIT_ROLES = [
  "musician",
  "mix engineer",
  "mastering engineer",
  "producer",
  "studio",
] as const;

function buildWizardUrl(
  basePath: string,
  opts: { fixedArtistId?: number; songId?: number | null },
): string {
  const params = new URLSearchParams();
  if (opts.fixedArtistId != null && opts.fixedArtistId > 0) {
    params.set("artist_id", String(opts.fixedArtistId));
  }
  if (opts.songId != null && opts.songId > 0) {
    params.set("id", String(opts.songId));
  }
  const q = params.toString();
  return q ? `${basePath}?${q}` : basePath;
}

function deriveWizardStep(
  song: SongDetail | null,
  hasSongId: boolean,
): 1 | 2 | 3 | 4 | null {
  if (!hasSongId) return 1;
  if (!song) return null;
  if (song.upload_status === "ready") return 4;
  if (!song.has_master_audio) return 2;
  if (!song.has_cover_art) return 3;
  return 4;
}

function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || seconds < 0 || !Number.isFinite(seconds)) return "—";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

type CreditRow = { name: string; role: (typeof CREDIT_ROLES)[number] };

type FeaturedPick = { id: number; name: string };

function MasterAudioLockedCard({ song }: { song: SongDetail }) {
  if (!song.has_master_audio) return null;
  return (
    <div className="rounded-xl border border-emerald-200/80 bg-emerald-50/80 p-4 dark:border-emerald-900/50 dark:bg-emerald-950/40">
      <p className="text-sm font-medium text-emerald-900 dark:text-emerald-100">
        <span className="mr-1.5" aria-hidden>
          ✔
        </span>
        Master uploaded
      </p>
      <p className="mt-2 text-sm text-emerald-800 dark:text-emerald-200">
        Duration:{" "}
        <span className="font-mono font-medium">
          {formatDuration(song.duration_seconds ?? null)}
        </span>
      </p>
      <p className="mt-3 flex items-start gap-2 text-sm text-emerald-900/90 dark:text-emerald-100/90">
        <span aria-hidden>🔒</span>
        <span>
          This file cannot be changed. To upload a different version, create a
          new song.
        </span>
      </p>
    </div>
  );
}

export type UploadWizardProps = {
  /** Base route for URL sync, e.g. `/upload` or `/artist-upload`. */
  basePath: string;
  /** When set, `artist_id` is fixed for metadata (not editable in UI). */
  fixedArtistId?: number;
  /** Rendered above the page title (e.g. artist hub nav). */
  headerSlot?: React.ReactNode;
  /**
   * When true, do not `router.replace` from localStorage when the URL has no `?id=`.
   * Use on /artist-upload when the parent shows an explicit “Continue” choice.
   */
  suppressStorageResumeRedirect?: boolean;
};

export function UploadWizard({
  basePath,
  fixedArtistId,
  headerSlot,
  suppressStorageResumeRedirect = false,
}: UploadWizardProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const idParam = searchParams.get("id");

  const [songId, setSongId] = useState<number | null>(null);
  const [song, setSong] = useState<SongDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [metadataError, setMetadataError] = useState<string | null>(null);
  const [audioError, setAudioError] = useState<string | null>(null);
  const [coverError, setCoverError] = useState<string | null>(null);
  const [coverBust, setCoverBust] = useState(0);

  const [title, setTitle] = useState("");
  const [artistId, setArtistId] = useState("");
  const [featuredPicks, setFeaturedPicks] = useState<FeaturedPick[]>([]);
  const [featuredQuery, setFeaturedQuery] = useState("");
  const [debouncedFeaturedQuery, setDebouncedFeaturedQuery] = useState("");
  const [featuredSearchResults, setFeaturedSearchResults] = useState<
    ArtistPublic[]
  >([]);
  const [featuredSearchLoading, setFeaturedSearchLoading] = useState(false);
  const [featuredSearchOpen, setFeaturedSearchOpen] = useState(false);
  const [creditRows, setCreditRows] = useState<CreditRow[]>([]);
  const [lockedArtistName, setLockedArtistName] = useState<string | null>(null);

  useEffect(() => {
    if (fixedArtistId != null && fixedArtistId > 0) {
      setArtistId(String(fixedArtistId));
    }
  }, [fixedArtistId]);

  useEffect(() => {
    if (fixedArtistId == null || fixedArtistId <= 0) {
      setLockedArtistName(null);
      return;
    }
    let cancelled = false;
    setLockedArtistName(null);
    void fetchArtist(fixedArtistId)
      .then((a) => {
        if (!cancelled) setLockedArtistName(a.name);
      })
      .catch(() => {
        if (!cancelled) setLockedArtistName(null);
      });
    return () => {
      cancelled = true;
    };
  }, [fixedArtistId]);

  const primaryArtistIdNum = useMemo(() => {
    if (fixedArtistId != null && fixedArtistId > 0) return fixedArtistId;
    const aid = parseInt(artistId, 10);
    return Number.isFinite(aid) && aid > 0 ? aid : null;
  }, [fixedArtistId, artistId]);

  useEffect(() => {
    const t = setTimeout(() => setDebouncedFeaturedQuery(featuredQuery), 300);
    return () => clearTimeout(t);
  }, [featuredQuery]);

  useEffect(() => {
    const q = debouncedFeaturedQuery.trim();
    if (q.length < 2) {
      setFeaturedSearchResults([]);
      setFeaturedSearchLoading(false);
      return;
    }
    let cancelled = false;
    setFeaturedSearchResults([]);
    setFeaturedSearchLoading(true);
    void searchArtists(q, 10)
      .then((data) => {
        if (!cancelled) setFeaturedSearchResults(data.artists ?? []);
      })
      .catch(() => {
        if (!cancelled) setFeaturedSearchResults([]);
      })
      .finally(() => {
        if (!cancelled) setFeaturedSearchLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [debouncedFeaturedQuery]);

  const refreshSong = useCallback(async (id: number) => {
    setLoadError(null);
    try {
      const data = await fetchSong(id);
      setSong(data);
    } catch (e) {
      setSong(null);
      setLoadError(
        e instanceof Error ? e.message : "We couldn’t load this song.",
      );
    }
  }, []);

  useEffect(() => {
    const fromUrl = idParam ? parseInt(idParam, 10) : NaN;
    if (Number.isFinite(fromUrl) && fromUrl > 0) {
      setSongId(fromUrl);
      void refreshSong(fromUrl);
      localStorage.setItem(STORAGE_KEY, String(fromUrl));
      return;
    }
    if (!suppressStorageResumeRedirect) {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const sid = parseInt(raw, 10);
        if (Number.isFinite(sid) && sid > 0) {
          router.replace(
            buildWizardUrl(basePath, {
              fixedArtistId,
              songId: sid,
            }),
          );
          return;
        }
      }
    }
    setSongId(null);
    setSong(null);
  }, [
    idParam,
    refreshSong,
    router,
    basePath,
    fixedArtistId,
    suppressStorageResumeRedirect,
  ]);

  const step = useMemo(
    () => deriveWizardStep(song, songId != null),
    [song, songId],
  );

  const persistSongId = (id: number) => {
    setSongId(id);
    localStorage.setItem(STORAGE_KEY, String(id));
    router.replace(
      buildWizardUrl(basePath, { fixedArtistId, songId: id }),
    );
  };

  const clearSession = () => {
    router.replace(buildWizardUrl(basePath, { fixedArtistId, songId: null }));
    localStorage.removeItem(STORAGE_KEY);
    setSongId(null);
    setSong(null);
    setTitle("");
    if (fixedArtistId == null) {
      setArtistId("");
    } else {
      setArtistId(String(fixedArtistId));
    }
    setFeaturedPicks([]);
    setFeaturedQuery("");
    setDebouncedFeaturedQuery("");
    setFeaturedSearchResults([]);
    setFeaturedSearchLoading(false);
    setFeaturedSearchOpen(false);
    setCreditRows([]);
    setMetadataError(null);
    setAudioError(null);
    setCoverError(null);
    setLoadError(null);
  };

  const resolvedArtistIdForSubmit = (): number | null => {
    if (fixedArtistId != null && fixedArtistId > 0) {
      return fixedArtistId;
    }
    const aid = parseInt(artistId, 10);
    return Number.isFinite(aid) ? aid : null;
  };

  const addFeaturedFromSearch = (artist: ArtistPublic) => {
    if (primaryArtistIdNum != null && artist.id === primaryArtistIdNum) {
      return;
    }
    setFeaturedPicks((prev) =>
      prev.some((p) => p.id === artist.id)
        ? prev
        : [...prev, { id: artist.id, name: artist.name }],
    );
    setFeaturedQuery("");
    setDebouncedFeaturedQuery("");
    setFeaturedSearchResults([]);
    setFeaturedSearchOpen(false);
    setMetadataError(null);
  };

  const visibleFeaturedSearchResults = useMemo(() => {
    return featuredSearchResults.filter(
      (a) =>
        (primaryArtistIdNum == null || a.id !== primaryArtistIdNum) &&
        !featuredPicks.some((p) => p.id === a.id),
    );
  }, [featuredSearchResults, primaryArtistIdNum, featuredPicks]);

  const showFeaturedSearchPanel =
    featuredSearchOpen && debouncedFeaturedQuery.trim().length >= 2;

  const submitMetadata = async () => {
    setMetadataError(null);
    if (!title.trim()) {
      setMetadataError("Please enter a title.");
      return;
    }
    const aid = resolvedArtistIdForSubmit();
    if (aid == null) {
      setMetadataError("Please enter a valid artist ID.");
      return;
    }
    setBusy(true);
    try {
      const featured_artist_ids = featuredPicks.map((p) => p.id);
      const credits = creditRows.filter((r) => r.name.trim());
      const res = await apiFetch(`/songs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: title.trim(),
          artist_id: aid,
          featured_artist_ids,
          credits: credits.map((c) => ({ name: c.name.trim(), role: c.role })),
        }),
      });
      if (!res.ok) {
        const { detail } = await parseErrorPayload(res);
        setMetadataError(
          detail || "Something went wrong while creating the song.",
        );
        return;
      }
      const data = (await res.json()) as { song_id: number };
      persistSongId(data.song_id);
      await refreshSong(data.song_id);
    } finally {
      setBusy(false);
    }
  };

  const submitAudio = async (file: File | null) => {
    setAudioError(null);
    if (!file || !songId) {
      setAudioError("Choose a WAV file to continue.");
      return;
    }
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await apiFetch(`/songs/${songId}/upload-audio`, {
        method: "POST",
        body: fd,
      });
      if (!res.ok) {
        const { code, detail } = await parseErrorPayload(res);
        if (code === "wav_file_too_large") {
          setAudioError("File too large (max 225MB)");
          return;
        }
        if (code === "master_audio_immutable") {
          setAudioError("Audio already uploaded");
          return;
        }
        setAudioError(
          detail || "Couldn’t upload audio. Check the file and try again.",
        );
        return;
      }
      await refreshSong(songId);
    } finally {
      setBusy(false);
    }
  };

  const submitCover = async (file: File | null) => {
    setCoverError(null);
    if (!file || !songId) {
      setCoverError("Choose a JPEG or PNG image.");
      return;
    }
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await apiFetch(`/songs/${songId}/upload-cover`, {
        method: "POST",
        body: fd,
      });
      if (!res.ok) {
        const { code, detail } = await parseErrorPayload(res);
        if (code === "cover_resolution_invalid") {
          setCoverError("Invalid resolution (1400–3000px required)");
          return;
        }
        setCoverError(
          detail || "Couldn’t upload cover. Check the image and try again.",
        );
        return;
      }
      setCoverBust((x) => x + 1);
      await refreshSong(songId);
    } finally {
      setBusy(false);
    }
  };

  const stepsMeta = [
    { n: 1 as const, label: "Metadata" },
    { n: 2 as const, label: "Audio" },
    { n: 3 as const, label: "Cover" },
    { n: 4 as const, label: "Ready" },
  ];

  const coverSrc =
    song?.cover_url != null
      ? `${API_BASE}${song.cover_url}?v=${coverBust}`
      : null;

  const artistLocked = fixedArtistId != null && fixedArtistId > 0;

  return (
    <main className="mx-auto max-w-2xl px-4 py-10">
      {headerSlot}
      <div className="mb-8 flex items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold tracking-tight">Upload a song</h1>
        <Link
          href="/"
          className="text-sm text-neutral-500 underline-offset-4 hover:underline"
        >
          Home
        </Link>
      </div>

      <ol className="mb-10 flex gap-2 border-b border-neutral-200 pb-4 dark:border-neutral-800">
        {stepsMeta.map(({ n, label }) => {
          const done =
            (n === 1 && songId != null) ||
            (n === 2 && !!song?.has_master_audio) ||
            (n === 3 && !!song?.has_cover_art) ||
            (n === 4 && song?.upload_status === "ready");
          const active = step != null ? step === n : n === 2;

          return (
            <li
              key={n}
              className={`flex flex-1 flex-col items-center gap-1.5 text-center text-xs sm:text-sm ${
                done
                  ? "font-medium text-emerald-800 dark:text-emerald-200"
                  : active
                    ? "font-semibold text-neutral-900 dark:text-neutral-100"
                    : "text-neutral-400 opacity-55 dark:text-neutral-500"
              }`}
            >
              <span
                className={`flex h-9 w-9 items-center justify-center rounded-full text-sm transition-shadow ${
                  done
                    ? "bg-emerald-600 text-white shadow-sm"
                    : active
                      ? "bg-neutral-900 text-white shadow-md ring-2 ring-neutral-900 ring-offset-2 ring-offset-white dark:bg-neutral-100 dark:text-neutral-900 dark:ring-neutral-100 dark:ring-offset-neutral-950"
                      : "bg-neutral-200 text-neutral-500 dark:bg-neutral-800 dark:text-neutral-400"
                }`}
                aria-current={active ? "step" : undefined}
              >
                {done ? "✔" : n}
              </span>
              <span className="hidden sm:inline">{label}</span>
            </li>
          );
        })}
      </ol>

      {songId != null && step === null && !loadError && (
        <p className="mb-6 text-sm text-neutral-500" aria-live="polite">
          Loading song…
        </p>
      )}

      {loadError && (
        <div
          className="mb-6 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-100"
          role="alert"
        >
          {loadError}
          <button
            type="button"
            onClick={clearSession}
            className="ml-3 underline"
          >
            Start over
          </button>
        </div>
      )}

      {song && (
        <div className="mb-6 flex flex-wrap items-center gap-3">
          <span className="text-sm text-neutral-500">Status</span>
          <span className="rounded-full bg-neutral-100 px-3 py-1 text-xs font-medium uppercase tracking-wide dark:bg-neutral-800">
            {song.upload_status}
          </span>
          <span className="text-sm text-neutral-500">
            Duration{" "}
            <span className="font-mono text-neutral-800 dark:text-neutral-200">
              {formatDuration(song.duration_seconds ?? null)}
            </span>
          </span>
        </div>
      )}

      {step === 1 && (
        <section className="space-y-6 rounded-xl border border-neutral-200 p-6 dark:border-neutral-800">
          <h2 className="text-lg font-medium">Song details</h2>
          <label className="block space-y-1">
            <span className="text-sm text-neutral-600 dark:text-neutral-400">
              Title
            </span>
            <input
              className="w-full rounded-lg border border-neutral-300 bg-white px-3 py-2 dark:border-neutral-700 dark:bg-neutral-950"
              value={title}
              onChange={(e) => {
                setTitle(e.target.value);
                setMetadataError(null);
              }}
              placeholder="Track title"
            />
          </label>
          {artistLocked ? (
            <div className="rounded-lg border border-neutral-200 bg-neutral-50 px-4 py-3 dark:border-neutral-700 dark:bg-neutral-900/40">
              <p className="text-sm text-neutral-500 dark:text-neutral-400">
                Artist
              </p>
              <p className="mt-1 text-base font-medium text-neutral-900 dark:text-neutral-100">
                {lockedArtistName != null ? (
                  <>
                    {lockedArtistName}{" "}
                    <span className="font-mono text-neutral-600 dark:text-neutral-400">
                      (ID {fixedArtistId})
                    </span>
                  </>
                ) : (
                  <span className="font-mono">ID {fixedArtistId}</span>
                )}
              </p>
              <p className="mt-1 text-xs text-neutral-500">
                Fixed for this session — cannot be changed here.
              </p>
            </div>
          ) : (
            <label className="block space-y-1">
              <span className="text-sm text-neutral-600 dark:text-neutral-400">
                Artist ID
              </span>
              <input
                type="number"
                min={1}
                className="w-full rounded-lg border border-neutral-300 bg-white px-3 py-2 font-mono dark:border-neutral-700 dark:bg-neutral-950"
                value={artistId}
                onChange={(e) => {
                  setArtistId(e.target.value);
                  setMetadataError(null);
                }}
                placeholder="e.g. 1"
              />
            </label>
          )}
          <div className="space-y-2">
            <span className="block text-sm text-neutral-600 dark:text-neutral-400">
              Add featured artists
            </span>
            <div className="relative">
              <input
                type="search"
                autoComplete="off"
                className="w-full rounded-lg border border-neutral-300 bg-white px-3 py-2 dark:border-neutral-700 dark:bg-neutral-950"
                value={featuredQuery}
                onChange={(e) => {
                  setFeaturedQuery(e.target.value);
                  setMetadataError(null);
                }}
                placeholder="Search artist…"
                onFocus={() => setFeaturedSearchOpen(true)}
                onBlur={() => {
                  window.setTimeout(() => setFeaturedSearchOpen(false), 200);
                }}
              />
              {showFeaturedSearchPanel && (
                <div
                  className="absolute left-0 right-0 top-full z-20 mt-1 max-h-56 overflow-auto rounded-lg border border-neutral-200 bg-white py-1 shadow-md dark:border-neutral-700 dark:bg-neutral-950"
                >
                  {featuredSearchLoading && (
                    <div className="flex items-center gap-2 px-3 py-2 text-sm text-neutral-500 dark:text-neutral-400">
                      <span
                        className="inline-block size-3 animate-spin rounded-full border-2 border-neutral-300 border-t-neutral-600 dark:border-neutral-600 dark:border-t-neutral-300"
                        aria-hidden
                      />
                      Searching…
                    </div>
                  )}
                  {!featuredSearchLoading &&
                    visibleFeaturedSearchResults.length === 0 && (
                      <div className="px-3 py-2 text-sm text-neutral-500 dark:text-neutral-400">
                        No artists found
                      </div>
                    )}
                  {!featuredSearchLoading &&
                    visibleFeaturedSearchResults.map((a) => (
                      <button
                        key={a.id}
                        type="button"
                        className="flex w-full px-3 py-2 text-left text-sm text-neutral-800 hover:bg-neutral-100 dark:text-neutral-100 dark:hover:bg-neutral-800"
                        onMouseDown={(e) => e.preventDefault()}
                        onClick={() => addFeaturedFromSearch(a)}
                      >
                        {a.name}{" "}
                        <span className="text-neutral-500 dark:text-neutral-400">
                          (ID {a.id})
                        </span>
                      </button>
                    ))}
                </div>
              )}
            </div>
            {featuredQuery.trim().length > 0 &&
              featuredQuery.trim().length < 2 && (
                <p className="text-xs text-neutral-500 dark:text-neutral-400">
                  Type at least 2 characters to search.
                </p>
              )}
            {featuredPicks.length > 0 && (
              <ul className="flex flex-wrap gap-2" aria-label="Featured artists">
                {featuredPicks.map((pick) => (
                  <li key={pick.id}>
                    <span className="inline-flex items-center gap-1 rounded-full border border-neutral-300 bg-white py-1 pl-3 pr-1 text-sm text-neutral-800 dark:border-neutral-600 dark:bg-neutral-950 dark:text-neutral-100">
                      <span>
                        {pick.name}{" "}
                        <span className="text-neutral-500 dark:text-neutral-400">
                          (ID {pick.id})
                        </span>
                      </span>
                      <button
                        type="button"
                        className="rounded-full px-2 py-0.5 text-neutral-500 hover:bg-neutral-100 hover:text-neutral-900 dark:hover:bg-neutral-800 dark:hover:text-neutral-100"
                        aria-label={`Remove featured artist ${pick.name}`}
                        onClick={() =>
                          setFeaturedPicks((prev) =>
                            prev.filter((x) => x.id !== pick.id),
                          )
                        }
                      >
                        ×
                      </button>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-sm text-neutral-600 dark:text-neutral-400">
                Credits
              </span>
              <button
                type="button"
                className="text-sm text-neutral-600 underline dark:text-neutral-400"
                onClick={() =>
                  setCreditRows((r) => [
                    ...r,
                    { name: "", role: "musician" },
                  ])
                }
              >
                Add credit
              </button>
            </div>
            {creditRows.map((row, i) => (
              <div key={i} className="flex flex-col gap-2 sm:flex-row">
                <input
                  className="flex-1 rounded-lg border border-neutral-300 bg-white px-3 py-2 dark:border-neutral-700 dark:bg-neutral-950"
                  placeholder="Name"
                  value={row.name}
                  onChange={(e) => {
                    const next = [...creditRows];
                    next[i] = { ...next[i], name: e.target.value };
                    setCreditRows(next);
                  }}
                />
                <select
                  className="rounded-lg border border-neutral-300 bg-white px-3 py-2 dark:border-neutral-700 dark:bg-neutral-950"
                  value={row.role}
                  onChange={(e) => {
                    const next = [...creditRows];
                    next[i] = {
                      ...next[i],
                      role: e.target.value as CreditRow["role"],
                    };
                    setCreditRows(next);
                  }}
                >
                  {CREDIT_ROLES.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  className="rounded-lg border border-neutral-300 px-3 py-2 text-sm dark:border-neutral-700"
                  onClick={() =>
                    setCreditRows((r) => r.filter((_, j) => j !== i))
                  }
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
          <button
            type="button"
            disabled={busy}
            onClick={submitMetadata}
            className="w-full rounded-lg bg-neutral-900 py-3 text-sm font-medium text-white disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900"
          >
            {busy ? "Creating…" : "Create song & continue"}
          </button>
          {metadataError && (
            <p
              className="text-sm text-red-600 dark:text-red-400"
              role="alert"
              id="metadata-error"
            >
              {metadataError}
            </p>
          )}
        </section>
      )}

      {step === 2 && song && (
        <section className="space-y-6 rounded-xl border border-neutral-200 p-6 dark:border-neutral-800">
          <h2 className="text-lg font-medium">Master audio (WAV)</h2>

          {song.has_master_audio ? (
            <>
              <MasterAudioLockedCard song={song} />
              <div>
                <label className="mb-2 block text-sm text-neutral-500 dark:text-neutral-400">
                  Replace master file
                </label>
                <input
                  type="file"
                  accept=".wav,audio/wav"
                  disabled
                  aria-disabled="true"
                  className="block w-full cursor-not-allowed opacity-50 file:mr-4 file:rounded-lg file:border-0 file:bg-neutral-200 file:px-4 file:py-2 dark:file:bg-neutral-800"
                />
                <p className="mt-1 text-xs text-neutral-500">
                  Upload disabled — master is locked for this song.
                </p>
              </div>
            </>
          ) : (
            <>
              <p className="text-base text-neutral-700 dark:text-neutral-300">
                Upload your master WAV file (max 225MB)
              </p>
              <p className="text-sm text-neutral-500 dark:text-neutral-400">
                After upload, this file cannot be replaced.
              </p>
              <div>
                <input
                  type="file"
                  accept=".wav,audio/wav"
                  disabled={busy}
                  aria-invalid={!!audioError}
                  aria-describedby={audioError ? "audio-error" : undefined}
                  className="block w-full text-sm file:mr-4 file:rounded-lg file:border-0 file:bg-neutral-100 file:px-4 file:py-2 dark:file:bg-neutral-800"
                  onChange={(e) => {
                    const f = e.target.files?.[0] ?? null;
                    void submitAudio(f);
                    e.target.value = "";
                  }}
                />
                {audioError && (
                  <p
                    id="audio-error"
                    className="mt-2 text-sm text-red-600 dark:text-red-400"
                    role="alert"
                  >
                    {audioError}
                  </p>
                )}
              </div>
            </>
          )}
        </section>
      )}

      {step === 3 && song && (
        <section className="space-y-6 rounded-xl border border-neutral-200 p-6 dark:border-neutral-800">
          <MasterAudioLockedCard song={song} />

          <h2 className="text-lg font-medium">Cover art</h2>
          <p className="text-base text-neutral-700 dark:text-neutral-300">
            Upload cover artwork (1400px–3000px)
          </p>
          <p className="text-sm text-neutral-500 dark:text-neutral-400">
            JPEG or PNG, width and height each between 1400 and 3000 pixels.
            You can replace the cover later if needed.
          </p>
          <div>
            <input
              type="file"
              accept="image/jpeg,image/png,.jpg,.jpeg,.png"
              disabled={busy}
              aria-invalid={!!coverError}
              aria-describedby={coverError ? "cover-error" : undefined}
              className="block w-full text-sm file:mr-4 file:rounded-lg file:border-0 file:bg-neutral-100 file:px-4 file:py-2 dark:file:bg-neutral-800"
              onChange={(e) => {
                const f = e.target.files?.[0] ?? null;
                void submitCover(f);
                e.target.value = "";
              }}
            />
            {coverError && (
              <p
                id="cover-error"
                className="mt-2 text-sm text-red-600 dark:text-red-400"
                role="alert"
              >
                {coverError}
              </p>
            )}
          </div>
        </section>
      )}

      {step === 4 && song && (
        <section className="space-y-6 rounded-xl border border-neutral-200 p-6 dark:border-neutral-800">
          <h2 className="text-lg font-medium">You&apos;re ready</h2>

          <MasterAudioLockedCard song={song} />

          <div className="space-y-2 text-sm">
            <p>
              <span className="text-neutral-500">Title</span>{" "}
              <span className="font-medium">{song.title}</span>
            </p>
            <p>
              <span className="text-neutral-500">Duration</span>{" "}
              <span className="font-mono">
                {formatDuration(song.duration_seconds ?? null)}
              </span>
            </p>
            <p className="flex items-center gap-2">
              <span className="text-neutral-500">Status</span>
              <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold uppercase text-emerald-900 dark:bg-emerald-900 dark:text-emerald-100">
                READY
              </span>
            </p>
          </div>
          {coverSrc && (
            <div>
              <p className="mb-2 text-sm text-neutral-500">Cover</p>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={coverSrc}
                alt="Cover"
                className="max-h-64 w-auto rounded-lg border border-neutral-200 object-contain dark:border-neutral-700"
              />
            </div>
          )}
          <Link
            href={`/song/${song.id}`}
            className="inline-flex w-full items-center justify-center rounded-lg bg-neutral-900 py-3 text-sm font-medium text-white dark:bg-neutral-100 dark:text-neutral-900"
          >
            View song
          </Link>
          <button
            type="button"
            onClick={clearSession}
            className="w-full text-sm text-neutral-500 underline"
          >
            Start another upload
          </button>
        </section>
      )}
    </main>
  );
}
