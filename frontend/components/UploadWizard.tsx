"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type SelectHTMLAttributes,
} from "react";
import {
  API_BASE,
  apiFetch,
  createSongWithRelease,
  fetchArtist,
  fetchGenres,
  fetchSong,
  fetchSubgenresForGenre,
  parseErrorPayload,
  patchSongMetadata,
  putSongSplits,
  searchArtists,
  type ArtistPublic,
  type SongDetail,
  type TaxonomyItem,
} from "@/lib/api";
import { ISO_COUNTRY_OPTIONS } from "@/lib/isoCountries";
import { UploadWizardPageLayout } from "@/components/UploadWizardPageLayout";

const STORAGE_KEY = "uploadWizardSongId";

const CREDIT_ROLES = [
  "songwriter",
  "composer",
  "arranger",
  "producer",
  "musician",
  "sound designer",
  "mix engineer",
  "mastering engineer",
  "artwork",
  "studio",
] as const;

/** Shared field chrome (Song details card + royalty rows). */
const WIZARD_FIELD_BASE =
  "rounded-lg border border-solid border-neutral-400 bg-white px-3 py-2 text-sm text-neutral-900 transition-[background-color,border-color,color] duration-150 ease-out dark:border-neutral-600 dark:bg-neutral-950 dark:text-neutral-100";

const WIZARD_INPUT_CLASS = `${WIZARD_FIELD_BASE} w-full placeholder:text-neutral-400 dark:placeholder:text-neutral-500`;

const WIZARD_INPUT_FLEX = `${WIZARD_FIELD_BASE} min-w-0 flex-1 placeholder:text-neutral-400 dark:placeholder:text-neutral-500`;

const WIZARD_SELECT_INNER = `${WIZARD_FIELD_BASE} w-full cursor-pointer appearance-none [-webkit-appearance:none] bg-white pr-10 dark:bg-neutral-950`;

const SECTION_TITLE = "text-lg font-medium text-neutral-900 dark:text-white";
const SECTION_LABEL =
  "text-sm font-medium text-neutral-900 dark:text-white";
const HELPER_TEXT = "text-xs text-neutral-500 dark:text-neutral-400";
const BRAND_ACCENT = "text-[#F37D25]";

function WizardSelect({
  className = "",
  children,
  ...rest
}: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <div className="relative w-full min-w-0">
      <select {...rest} className={`${WIZARD_SELECT_INNER} ${className}`}>
        {children}
      </select>
      <span
        aria-hidden
        className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 select-none text-[10px] text-neutral-400"
      >
        ▼
      </span>
    </div>
  );
}

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
  opts: { mode: "single" | "album-track"; albumCoverAdvance: boolean },
): 1 | 2 | 3 | 4 | null {
  if (!hasSongId) return 1;
  if (!song) return null;
  if (opts.mode === "album-track") {
    if (!song.has_master_audio) return 2;
    if (!opts.albumCoverAdvance) return 3;
    if (song.upload_status === "ready") return 4;
    return 3;
  }
  /* Standalone single: open step 1 when ready so catalog "Edit" can change unlocked fields. */
  if (song.upload_status === "ready") return 1;
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

const MAX_MOODS = 10;
const MAX_MOOD_LEN = 32;

function parseMoodsFromInput(raw: string): string[] {
  return raw
    .split(",")
    .map((m) => m.trim())
    .filter(Boolean)
    .map((m) => m.slice(0, MAX_MOOD_LEN));
}

type RoyaltySplitRowState = {
  artist_id: number | null;
  share: number;
};

function validateSplitRowsForSubmit(rows: RoyaltySplitRowState[]): string | null {
  if (rows.length === 0) return "Add at least one royalty split row.";
  if (
    rows.some(
      (r) =>
        r.artist_id == null ||
        !Number.isFinite(r.artist_id) ||
        r.artist_id < 1,
    )
  ) {
    return "Select an artist for every split row (search and pick from results).";
  }
  const ids = rows.map((r) => r.artist_id as number);
  if (new Set(ids).size !== ids.length) {
    return "Each artist can only appear once in splits.";
  }
  const sum = rows.reduce((a, r) => a + (Number.isFinite(r.share) ? r.share : 0), 0);
  if (Math.abs(sum - 1) > 0.001) {
    return "Royalty shares must add up to 100% (1.0).";
  }
  return null;
}

function splitsToApiPayload(
  rows: RoyaltySplitRowState[],
): { artist_id: number; share: number }[] {
  return rows
    .filter((r): r is { artist_id: number; share: number } => r.artist_id != null)
    .map((r) => ({
      artist_id: r.artist_id,
      share: Number(r.share.toFixed(6)),
    }));
}

function RoyaltySplitRow({
  row,
  canRemove,
  excludeArtistIds,
  resolvedName,
  locked,
  onPickArtist,
  onClearArtist,
  onShareChange,
  onRemove,
}: {
  row: RoyaltySplitRowState;
  canRemove: boolean;
  excludeArtistIds: number[];
  /** From parent cache / fetch; not stored on `row` */
  resolvedName?: string | null;
  locked?: boolean;
  onPickArtist: (artist: ArtistPublic) => void;
  onClearArtist: () => void;
  onShareChange: (share01: number) => void;
  onRemove: () => void;
}) {
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [searchResults, setSearchResults] = useState<ArtistPublic[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);

  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedQuery(query), 300);
    return () => window.clearTimeout(t);
  }, [query]);

  useEffect(() => {
    const q = debouncedQuery.trim();
    if (q.length < 2) {
      setSearchResults([]);
      setSearchLoading(false);
      return;
    }
    let cancelled = false;
    setSearchResults([]);
    setSearchLoading(true);
    void searchArtists(q, 10)
      .then((data) => {
        if (!cancelled) setSearchResults(data.artists ?? []);
      })
      .catch(() => {
        if (!cancelled) setSearchResults([]);
      })
      .finally(() => {
        if (!cancelled) setSearchLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [debouncedQuery]);

  const visibleResults = useMemo(
    () => searchResults.filter((a) => !excludeArtistIds.includes(a.id)),
    [searchResults, excludeArtistIds],
  );

  const showSearchPanel =
    searchOpen && debouncedQuery.trim().length >= 2 && row.artist_id == null;

  const reopenArtistSearch = () => {
    setQuery("");
    setDebouncedQuery("");
    setSearchResults([]);
    setSearchOpen(true);
    onClearArtist();
  };

  const displayArtist =
    row.artist_id != null
      ? `${(resolvedName?.trim() || "Artist").trim()} (ID ${row.artist_id})`
      : null;

  const readOnly = !!locked;

  return (
    <div
      className={`flex flex-col gap-2 rounded-lg border border-neutral-200 p-3 dark:border-neutral-700 sm:flex-row sm:items-end ${readOnly ? "opacity-70" : ""}`}
    >
      <div className="relative min-w-0 flex-1 space-y-1">
        <span className="text-xs text-neutral-500 dark:text-neutral-400">
          Artist
        </span>
        {row.artist_id != null ? (
          <button
            type="button"
            disabled={readOnly}
            className="flex max-w-full items-center gap-1.5 rounded-md px-1 py-0.5 text-left text-sm text-neutral-800 hover:bg-neutral-100 disabled:cursor-not-allowed disabled:opacity-60 dark:text-neutral-100 dark:hover:bg-neutral-800"
            onClick={readOnly ? undefined : reopenArtistSearch}
            aria-label="Change artist — search again"
          >
            <span aria-hidden className="shrink-0 text-neutral-500">
              ✏️
            </span>
            <span className="min-w-0 truncate">{displayArtist}</span>
          </button>
        ) : (
          <>
            <input
              type="search"
              autoComplete="off"
              disabled={readOnly}
              className={WIZARD_INPUT_CLASS}
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
              }}
              placeholder="Search artist…"
              onFocus={() => setSearchOpen(true)}
              onBlur={() => {
                window.setTimeout(() => setSearchOpen(false), 200);
              }}
            />
            {showSearchPanel && (
              <div className="absolute left-0 right-0 top-full z-20 mt-1 max-h-56 overflow-auto rounded-lg border border-neutral-200 bg-white py-1 shadow-md dark:border-neutral-700 dark:bg-neutral-950">
                {searchLoading && (
                  <div className="flex items-center gap-2 px-3 py-2 text-sm text-neutral-500 dark:text-neutral-400">
                    <span
                      className="inline-block size-3 animate-spin rounded-full border-2 border-neutral-300 border-t-neutral-600 dark:border-neutral-600 dark:border-t-neutral-300"
                      aria-hidden
                    />
                    Searching…
                  </div>
                )}
                {!searchLoading && visibleResults.length === 0 && (
                  <div className="px-3 py-2 text-sm text-neutral-500 dark:text-neutral-400">
                    No artists found
                  </div>
                )}
                {!searchLoading &&
                  visibleResults.map((a) => (
                    <button
                      key={a.id}
                      type="button"
                      className="flex w-full px-3 py-2 text-left text-sm text-neutral-800 hover:bg-neutral-100 dark:text-neutral-100 dark:hover:bg-neutral-800"
                      onMouseDown={(e) => e.preventDefault()}
                      onClick={() => {
                        onPickArtist(a);
                        setQuery("");
                        setDebouncedQuery("");
                        setSearchResults([]);
                        setSearchOpen(false);
                      }}
                    >
                      {a.name}{" "}
                      <span className="text-neutral-500 dark:text-neutral-400">
                        (ID {a.id})
                      </span>
                    </button>
                  ))}
              </div>
            )}
            {query.trim().length > 0 && query.trim().length < 2 && (
              <p className="text-xs text-neutral-500 dark:text-neutral-400">
                Type at least 2 characters to search.
              </p>
            )}
          </>
        )}
      </div>
      <label className="block w-full min-w-0 sm:w-32 space-y-1">
        <span className="text-xs text-neutral-500 dark:text-neutral-400">
          Share %
        </span>
        <input
          type="number"
          min={0}
          max={100}
          step={0.1}
          disabled={readOnly}
          className={WIZARD_INPUT_CLASS}
          value={
            Number.isFinite(row.share) ? Math.round(row.share * 1000) / 10 : 0
          }
          onChange={(e) => {
            const v = parseFloat(e.target.value);
            const pct = Number.isFinite(v)
              ? Math.min(100, Math.max(0, v))
              : 0;
            onShareChange(pct / 100);
          }}
        />
      </label>
      {canRemove && !readOnly ? (
        <button
          type="button"
          className="rounded-lg border border-neutral-300 px-3 py-2 text-sm dark:border-neutral-700"
          onClick={() => {
            onRemove();
          }}
        >
          Remove
        </button>
      ) : null}
    </div>
  );
}

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
  basePath?: string;
  /** When set, `artist_id` is fixed for metadata (not editable in UI). */
  fixedArtistId?: number;
  /** Rendered above the page title (e.g. artist hub nav). */
  headerSlot?: React.ReactNode;
  /**
   * When true, do not `router.replace` from localStorage when the URL has no `?id=`.
   * Use on /artist-upload when the parent shows an explicit “Continue” choice.
   */
  suppressStorageResumeRedirect?: boolean;
  mode?: "single" | "album-track";
  /** Required when `mode === "album-track"`. */
  releaseId?: number;
  albumTitle?: string;
  trackIndex?: number;
  trackCount?: number;
  /** When embedding for album: existing song to edit, or null for a new track. */
  initialSongId?: number | null;
  onAlbumTrackSaved?: () => void;
};

export function UploadWizard({
  basePath = "/artist-upload",
  fixedArtistId,
  headerSlot,
  suppressStorageResumeRedirect = false,
  mode = "single",
  releaseId,
  albumTitle = "",
  trackIndex = 1,
  trackCount = 1,
  initialSongId,
  onAlbumTrackSaved,
}: UploadWizardProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const idParam =
    searchParams.get("id") ?? searchParams.get("song_id") ?? undefined;
  const isAlbumTrack = mode === "album-track";

  const [songId, setSongId] = useState<number | null>(null);
  const [albumCoverAdvance, setAlbumCoverAdvance] = useState(false);
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
  const [creditRows, setCreditRows] = useState<CreditRow[]>([
    { name: "", role: "musician" },
  ]);

  const [genres, setGenres] = useState<TaxonomyItem[]>([]);
  const [genresLoading, setGenresLoading] = useState(false);
  const [genresError, setGenresError] = useState<string | null>(null);
  const [genreId, setGenreId] = useState<number | null>(null);
  const [subgenreId, setSubgenreId] = useState<number | null>(null);
  const [subgenres, setSubgenres] = useState<TaxonomyItem[]>([]);
  const [subgenresLoading, setSubgenresLoading] = useState(false);

  const [moodInput, setMoodInput] = useState("");
  const [countryCode, setCountryCode] = useState("");
  const [city, setCity] = useState("");
  const [royaltySplitOpen, setRoyaltySplitOpen] = useState(false);
  const [splitRows, setSplitRows] = useState<RoyaltySplitRowState[]>([]);
  const [splitsEditedByUser, setSplitsEditedByUser] = useState(false);
  const [splitArtistDisplayNames, setSplitArtistDisplayNames] = useState<
    Record<number, string>
  >({});

  const metadataLocked = useMemo(
    () => song != null && String(song.upload_status).toLowerCase() === "ready",
    [song],
  );

  const hydratedSongIdRef = useRef<number | null>(null);

  useEffect(() => {
    if (metadataLocked) {
      setRoyaltySplitOpen(false);
    }
  }, [metadataLocked]);

  useEffect(() => {
    if (songId == null) {
      hydratedSongIdRef.current = null;
      return;
    }
    if (song == null || song.id !== songId) return;
    if (hydratedSongIdRef.current === songId) return;
    hydratedSongIdRef.current = songId;

    let cancelled = false;

    setTitle(song.title || "");
    setMoodInput(
      song.moods != null && song.moods.length > 0 ? song.moods.join(", ") : "",
    );
    setCountryCode((song.country_code || "").trim().toUpperCase());
    setCity(song.city?.trim() ?? "");

    const cr = song.credits ?? [];
    if (cr.length > 0) {
      setCreditRows(
        cr.map((c) => ({
          name: c.name,
          role: (CREDIT_ROLES as readonly string[]).includes(c.role)
            ? (c.role as CreditRow["role"])
            : "musician",
        })),
      );
    } else {
      setCreditRows([{ name: "", role: "musician" }]);
    }

    const splits = song.splits ?? [];
    const primaryAid = song.artist_id;
    if (splits.length > 0) {
      setSplitRows(
        splits.map((s) => ({
          artist_id: s.artist_id,
          share: s.share,
        })),
      );
      setSplitsEditedByUser(true);
    } else {
      setSplitRows([{ artist_id: primaryAid, share: 1 }]);
      setSplitsEditedByUser(false);
    }

    void (async () => {
      const ids = song.featured_artist_ids ?? [];
      const picks: FeaturedPick[] = [];
      for (const fid of ids) {
        try {
          const a = await fetchArtist(fid);
          picks.push({ id: a.id, name: a.name });
        } catch {
          picks.push({ id: fid, name: `Artist #${fid}` });
        }
      }
      if (!cancelled) setFeaturedPicks(picks);
    })();

    return () => {
      cancelled = true;
    };
  }, [song, songId]);

  useEffect(() => {
    let cancelled = false;
    setGenresLoading(true);
    setGenresError(null);
    void fetchGenres()
      .then((list) => {
        if (!cancelled) setGenres(list);
      })
      .catch((e) => {
        if (!cancelled) {
          setGenresError(
            e instanceof Error ? e.message : "Could not load genres.",
          );
        }
      })
      .finally(() => {
        if (!cancelled) setGenresLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (genreId == null) {
      setSubgenres([]);
      setSubgenresLoading(false);
      return;
    }
    let cancelled = false;
    setSubgenresLoading(true);
    void fetchSubgenresForGenre(genreId)
      .then((list) => {
        if (!cancelled) setSubgenres(list);
      })
      .catch(() => {
        if (!cancelled) setSubgenres([]);
      })
      .finally(() => {
        if (!cancelled) setSubgenresLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [genreId]);

  /** Label for selected chip: list first, then nested object from GET /songs/{id}. */
  const selectedSubgenreName = useMemo(() => {
    if (subgenreId == null) return null;
    const fromList = subgenres.find((s) => s.id === subgenreId)?.name;
    if (fromList) return fromList;
    if (
      song != null &&
      song.subgenre_id === subgenreId &&
      song.subgenre?.name
    ) {
      return song.subgenre.name;
    }
    return null;
  }, [subgenreId, subgenres, song]);

  /** Sync taxonomy from backend whenever the loaded song matches the active id. */
  useEffect(() => {
    if (songId == null || song == null || song.id !== songId) return;
    const gid =
      song.genre_id != null && Number.isFinite(song.genre_id)
        ? song.genre_id
        : null;
    const sgid =
      song.subgenre_id != null && Number.isFinite(song.subgenre_id)
        ? song.subgenre_id
        : null;
    setGenreId(gid);
    setSubgenreId(sgid);
    if (gid == null) {
      setSubgenres([]);
    }
  }, [songId, song?.id, song?.genre_id, song?.subgenre_id]);

  const selectGenre = (id: number) => {
    setGenreId(id);
    setSubgenreId(null);
    setMetadataError(null);
  };

  useEffect(() => {
    if (fixedArtistId != null && fixedArtistId > 0) {
      setArtistId(String(fixedArtistId));
    }
  }, [fixedArtistId]);

  const primaryArtistIdNum = useMemo(() => {
    if (fixedArtistId != null && fixedArtistId > 0) return fixedArtistId;
    const aid = parseInt(artistId, 10);
    return Number.isFinite(aid) && aid > 0 ? aid : null;
  }, [fixedArtistId, artistId]);

  useEffect(() => {
    if (primaryArtistIdNum == null) return;
    if (!splitsEditedByUser) {
      setSplitRows([{ artist_id: primaryArtistIdNum, share: 1 }]);
    }
  }, [primaryArtistIdNum, splitsEditedByUser]);

  useEffect(() => {
    const need = new Set<number>();
    for (const r of splitRows) {
      if (
        r.artist_id != null &&
        r.artist_id >= 1 &&
        !splitArtistDisplayNames[r.artist_id]
      ) {
        need.add(r.artist_id);
      }
    }
    if (need.size === 0) return;
    let cancelled = false;
    need.forEach((id) => {
      void fetchArtist(id).then((a) => {
        if (cancelled) return;
        setSplitArtistDisplayNames((prev) =>
          prev[id] ? prev : { ...prev, [id]: a.name },
        );
      });
    });
    return () => {
      cancelled = true;
    };
  }, [splitRows, splitArtistDisplayNames]);

  const royaltyCollapsedSummary = useMemo(() => {
    if (splitRows.length === 0) return "100% to primary artist";
    if (splitRows.length === 1) {
      const r = splitRows[0];
      const pct = Math.round(r.share * 1000) / 10;
      const aid = r.artist_id;
      const name =
        aid != null && aid >= 1
          ? splitArtistDisplayNames[aid]?.trim() || `Artist #${aid}`
          : "primary artist";
      return `${pct}% to ${name}`;
    }
    return `${splitRows.length} artists — custom split`;
  }, [splitRows, splitArtistDisplayNames]);

  const royaltySplitInlineError = useMemo(() => {
    if (!royaltySplitOpen) return null;
    return validateSplitRowsForSubmit(splitRows);
  }, [splitRows, royaltySplitOpen]);

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

  const refreshSong = useCallback(async (id: number): Promise<SongDetail | null> => {
    setLoadError(null);
    try {
      const data = await fetchSong(id);
      setSong(data);
      return data;
    } catch (e) {
      setSong(null);
      setLoadError(
        e instanceof Error ? e.message : "We couldn’t load this song.",
      );
      return null;
    }
  }, []);

  useEffect(() => {
    if (isAlbumTrack) {
      setAlbumCoverAdvance(false);
    }
  }, [isAlbumTrack, initialSongId, releaseId]);

  useEffect(() => {
    if (!isAlbumTrack || song == null || songId == null || initialSongId == null) {
      return;
    }
    if (
      song.id === initialSongId &&
      song.has_master_audio &&
      song.upload_status === "ready"
    ) {
      setAlbumCoverAdvance(true);
    }
  }, [isAlbumTrack, song, songId, initialSongId]);

  useEffect(() => {
    if (
      !isAlbumTrack ||
      !albumCoverAdvance ||
      songId == null ||
      song?.upload_status === "ready"
    ) {
      return;
    }
    const t = window.setInterval(() => {
      void refreshSong(songId);
    }, 2000);
    return () => window.clearInterval(t);
  }, [
    isAlbumTrack,
    albumCoverAdvance,
    songId,
    song?.upload_status,
    refreshSong,
  ]);

  useEffect(() => {
    if (isAlbumTrack) {
      if (initialSongId != null && initialSongId > 0) {
        setSongId(initialSongId);
        void refreshSong(initialSongId);
      } else {
        setSongId(null);
        setSong(null);
      }
      return;
    }
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
    isAlbumTrack,
    initialSongId,
    idParam,
    refreshSong,
    router,
    basePath,
    fixedArtistId,
    suppressStorageResumeRedirect,
  ]);

  const step = useMemo(
    () =>
      deriveWizardStep(song, songId != null, {
        mode,
        albumCoverAdvance,
      }),
    [song, songId, mode, albumCoverAdvance],
  );

  const persistSongId = (id: number) => {
    setSongId(id);
    if (isAlbumTrack) {
      void refreshSong(id);
      return;
    }
    localStorage.setItem(STORAGE_KEY, String(id));
    router.replace(
      buildWizardUrl(basePath, { fixedArtistId, songId: id }),
    );
  };

  const clearSession = () => {
    if (!isAlbumTrack) {
      router.replace(buildWizardUrl(basePath, { fixedArtistId, songId: null }));
      localStorage.removeItem(STORAGE_KEY);
    }
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
    setCreditRows([{ name: "", role: "musician" }]);
    setGenreId(null);
    setSubgenreId(null);
    setSubgenres([]);
    setGenresError(null);
    setMetadataError(null);
    setAudioError(null);
    setCoverError(null);
    setLoadError(null);
    setAlbumCoverAdvance(false);
    setMoodInput("");
    setCountryCode("");
    setCity("");
    setRoyaltySplitOpen(false);
    setSplitRows([]);
    setSplitsEditedByUser(false);
    setSplitArtistDisplayNames({});
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
      setMetadataError("Title is required");
      return;
    }
    const aid = resolvedArtistIdForSubmit();
    if (aid == null) {
      setMetadataError("Please enter a valid artist ID.");
      return;
    }
    if (isAlbumTrack) {
      if (releaseId == null || releaseId <= 0) {
        setMetadataError("Missing release. Go back to album setup.");
        return;
      }
    }
    if (genreId == null) {
      setMetadataError("Please select a genre.");
      return;
    }

    const moods = parseMoodsFromInput(moodInput);
    if (moods.length > MAX_MOODS) {
      setMetadataError(`At most ${MAX_MOODS} moods (comma-separated).`);
      return;
    }
    const cityTrimmed = city.trim();
    if (cityTrimmed.length > 128) {
      setMetadataError("City must be at most 128 characters.");
      return;
    }
    const countryUpper = countryCode.trim().toUpperCase();
    if (cityTrimmed.length > 0 && countryUpper.length === 0) {
      setMetadataError("Select a country when entering a city.");
      return;
    }
    if (countryUpper.length > 0 && countryUpper.length !== 2) {
      setMetadataError("Country must be a 2-letter ISO code.");
      return;
    }

    const splitErr = metadataLocked
      ? null
      : validateSplitRowsForSubmit(splitRows);
    if (splitErr) {
      setRoyaltySplitOpen(true);
      setMetadataError(splitErr);
      return;
    }

    const metaFields = {
      ...(moods.length > 0 ? { moods } : {}),
      ...(countryUpper.length > 0 ? { country_code: countryUpper } : {}),
      ...(cityTrimmed.length > 0 ? { city: cityTrimmed } : {}),
    };

    const featured_artist_ids = featuredPicks.map((p) => p.id);
    const credits = creditRows
      .filter((r) => r.name.trim())
      .map((c) => ({ name: c.name.trim(), role: c.role }));

    setBusy(true);
    try {
      if (songId != null && !isAlbumTrack) {
        try {
          await patchSongMetadata(songId, {
            title: title.trim(),
            artist_id: aid,
            featured_artist_ids,
            credits,
            genre_id: genreId,
            subgenre_id: subgenreId ?? null,
            ...metaFields,
          });
        } catch (e) {
          setMetadataError(
            e instanceof Error
              ? e.message
              : "Something went wrong while saving metadata.",
          );
          return;
        }
        if (!metadataLocked && splitsEditedByUser) {
          try {
            await putSongSplits(songId, splitsToApiPayload(splitRows));
          } catch (e) {
            setMetadataError(
              e instanceof Error
                ? `${e.message} Metadata was saved; you can adjust splits later.`
                : "Splits could not be saved. Metadata was saved.",
            );
            return;
          }
        }
        await refreshSong(songId);
        return;
      }

      let createdId: number;

      if (isAlbumTrack && releaseId != null) {
        try {
          const data = await createSongWithRelease({
            title: title.trim(),
            artist_id: aid,
            release_id: releaseId,
            featured_artist_ids,
            credits,
            genre_id: genreId,
            subgenre_id: subgenreId ?? null,
            ...metaFields,
          });
          createdId = data.song_id;
        } catch (e) {
          setMetadataError(
            e instanceof Error
              ? e.message
              : "Something went wrong while creating the song.",
          );
          return;
        }
        setAlbumCoverAdvance(false);
      } else {
        const res = await apiFetch(`/songs`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            title: title.trim(),
            artist_id: aid,
            featured_artist_ids,
            credits,
            genre_id: genreId,
            subgenre_id: subgenreId ?? null,
            ...metaFields,
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
        createdId = data.song_id;
      }

      persistSongId(createdId);
      await refreshSong(createdId);

      if (splitsEditedByUser) {
        try {
          await putSongSplits(createdId, splitsToApiPayload(splitRows));
        } catch (e) {
          setMetadataError(
            e instanceof Error
              ? `${e.message} The song was created; you can adjust splits later.`
              : "Splits could not be saved. The song was created.",
          );
        }
      }
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
    if (isAlbumTrack) return;
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
    <UploadWizardPageLayout>
      {/* EXPRESSION_LAYER: reserved for future illustration/motion integration */}
      {headerSlot}
      <div className="mb-8 flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {isAlbumTrack ? "Album track" : "Upload a song"}
          </h1>
          {isAlbumTrack && (
            <p className="mt-2 text-sm text-neutral-600 dark:text-neutral-400">
              <span className="font-medium text-neutral-800 dark:text-neutral-200">
                Track {trackIndex} of {Math.max(trackCount, 1)}
              </span>
              {albumTitle.trim() ? (
                <>
                  <span className="mx-2 text-neutral-400">·</span>
                  <span>Album: {albumTitle.trim()}</span>
                </>
              ) : null}
            </p>
          )}
        </div>
        {!isAlbumTrack && (
          <Link
            href="/"
            className="text-sm text-neutral-500 underline-offset-4 hover:underline"
          >
            Home
          </Link>
        )}
      </div>

      <ol className="mb-10 flex gap-2 border-b border-neutral-200 pb-4 dark:border-neutral-800">
        {stepsMeta.map(({ n, label }) => {
          const coverStepDone = isAlbumTrack
            ? albumCoverAdvance
            : !!song?.has_cover_art;
          const done =
            (n === 1 && songId != null) ||
            (n === 2 && !!song?.has_master_audio) ||
            (n === 3 && coverStepDone) ||
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
          <h2 className={SECTION_TITLE}>Song details</h2>
          <label className="block space-y-1">
            <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <span className={`flex items-center gap-1.5 ${SECTION_LABEL}`}>
                Title
                {title.trim() ? (
                  <span className={BRAND_ACCENT} aria-hidden>
                    ✔
                  </span>
                ) : null}
              </span>
              <span className="text-sm font-normal text-red-600 dark:text-red-400">
                (required)
              </span>
            </span>
            <input
              className={WIZARD_INPUT_CLASS}
              value={title}
              disabled={metadataLocked}
              onChange={(e) => {
                setTitle(e.target.value);
                setMetadataError(null);
              }}
              placeholder="Track title"
              aria-invalid={!title.trim() && metadataError === "Title is required"}
              aria-describedby={
                !title.trim() && metadataError === "Title is required"
                  ? "title-required-error"
                  : undefined
              }
            />
            {metadataLocked ? (
              <p className={`mt-1 ${HELPER_TEXT}`}>
                Title is locked because this song is already marked ready.
              </p>
            ) : null}
            {!title.trim() && metadataError === "Title is required" ? (
              <p
                id="title-required-error"
                className="text-sm text-red-600 dark:text-red-400"
                role="alert"
              >
                Title is required
              </p>
            ) : null}
          </label>
          <div className="space-y-2">
            <span className={`block ${SECTION_LABEL}`}>Add featured artists</span>
            <div className="relative">
              <input
                type="search"
                autoComplete="off"
                disabled={metadataLocked}
                className={WIZARD_INPUT_CLASS}
                value={featuredQuery}
                onChange={(e) => {
                  setFeaturedQuery(e.target.value);
                  setFeaturedSearchOpen(true);
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
                    <span
                      className={`inline-flex items-center gap-1 rounded-full border border-neutral-300 bg-white py-1 pl-3 text-sm text-neutral-800 dark:border-neutral-600 dark:bg-neutral-950 dark:text-neutral-100 ${metadataLocked ? "pr-3 opacity-80" : "pr-1"}`}
                    >
                      <span>
                        {pick.name}{" "}
                        <span className="text-neutral-500 dark:text-neutral-400">
                          (ID {pick.id})
                        </span>
                      </span>
                      {!metadataLocked ? (
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
                      ) : null}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {metadataLocked ? (
              <p className={HELPER_TEXT}>
                Featured artists are locked while the song is ready.
              </p>
            ) : null}
          </div>
          {!artistLocked && (
            <label className="block space-y-1">
              <span className={`${HELPER_TEXT} text-sm`}>Artist ID</span>
              <input
                type="number"
                min={1}
                className={`${WIZARD_INPUT_CLASS} font-mono`}
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
            <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <span className={`flex items-center gap-1.5 ${SECTION_LABEL}`}>
                Genre
                {genreId != null ? (
                  <span className={BRAND_ACCENT} aria-hidden>
                    ✔
                  </span>
                ) : null}
              </span>
              <span className="text-sm font-normal text-red-600 dark:text-red-400">
                (required)
              </span>
            </span>
            {genresLoading && (
              <p className="text-sm text-neutral-500 dark:text-neutral-400">
                Loading genres…
              </p>
            )}
            {genresError && (
              <p className="text-sm text-red-600 dark:text-red-400" role="alert">
                {genresError}
              </p>
            )}
            {!genresLoading && genres.length > 0 && (
              <div
                className="flex flex-wrap gap-2"
                role="listbox"
                aria-label="Genres"
              >
                {genres.map((g) => {
                  const selected = genreId === g.id;
                  return (
                    <button
                      key={g.id}
                      type="button"
                      role="option"
                      aria-selected={selected}
                      onClick={() => selectGenre(g.id)}
                      className={`rounded-lg border px-3 py-2 text-sm font-medium transition-[background-color,border-color,color] duration-150 ease-out ${
                        selected
                          ? "border-neutral-900 bg-neutral-900 text-white dark:border-neutral-100 dark:bg-neutral-100 dark:text-neutral-900"
                          : "border-neutral-200 bg-white text-neutral-600 hover:bg-neutral-50 dark:border-neutral-600 dark:bg-neutral-950 dark:text-neutral-300 dark:hover:bg-neutral-900"
                      }`}
                    >
                      {g.name}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
          {genreId != null && (
            <div className="space-y-2">
              <span className={`block ${SECTION_LABEL}`}>Subgenre</span>
              {subgenresLoading && (
                <p className="text-sm text-neutral-500 dark:text-neutral-400">
                  Loading subgenres…
                </p>
              )}
              {!subgenresLoading && subgenres.length === 0 && (
                <p className="text-sm text-neutral-500 dark:text-neutral-400">
                  No subgenres for this genre.
                </p>
              )}
              {!subgenresLoading && subgenres.length > 0 && (
                <ul
                  className="max-h-40 space-y-1 overflow-y-auto rounded-lg border border-neutral-300 p-2 dark:border-neutral-700"
                  aria-label="Subgenres for selected genre"
                >
                  {subgenres.map((s) => {
                    const picked = subgenreId === s.id;
                    return (
                      <li key={s.id}>
                        <button
                          type="button"
                          onClick={() => {
                            setSubgenreId(s.id);
                            setMetadataError(null);
                          }}
                          className={`w-full rounded-md px-2 py-1.5 text-left text-sm ${
                            picked
                              ? "bg-neutral-900 font-medium text-white dark:bg-neutral-100 dark:text-neutral-900"
                              : "text-neutral-800 hover:bg-neutral-100 dark:text-neutral-100 dark:hover:bg-neutral-800"
                          }`}
                        >
                          {s.name}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
              {subgenreId != null && (
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm text-neutral-600 dark:text-neutral-400">
                    Selected:
                  </span>
                  <span className="inline-flex items-center gap-1 rounded-full border border-neutral-300 bg-white py-1 pl-3 pr-1 text-sm text-neutral-800 dark:border-neutral-600 dark:bg-neutral-950 dark:text-neutral-100">
                    <span>
                      {selectedSubgenreName ?? `Subgenre #${subgenreId}`}
                    </span>
                    <button
                      type="button"
                      className="rounded-full px-2 py-0.5 text-neutral-500 hover:bg-neutral-100 hover:text-neutral-900 dark:hover:bg-neutral-800 dark:hover:text-neutral-100"
                      aria-label="Clear subgenre"
                      onClick={() => {
                        setSubgenreId(null);
                        setMetadataError(null);
                      }}
                    >
                      <span aria-hidden>✕</span>
                    </button>
                  </span>
                </div>
              )}
            </div>
          )}
          <div className="mt-8 space-y-3 border-t border-neutral-200 pt-6 dark:border-neutral-800">
            <div>
              <span className={SECTION_LABEL}>Credits</span>
              <p className={`mt-0.5 ${HELPER_TEXT}`}>who worked on this track</p>
            </div>
            <div className="space-y-3">
              {creditRows.map((row, i) => (
                <div key={i} className="flex flex-col gap-2 sm:flex-row">
                  <input
                    className={WIZARD_INPUT_FLEX}
                    placeholder="Name"
                    value={row.name}
                    onChange={(e) => {
                      const next = [...creditRows];
                      next[i] = { ...next[i], name: e.target.value };
                      setCreditRows(next);
                    }}
                  />
                  <div className="sm:max-w-[12rem] sm:flex-1">
                    <WizardSelect
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
                    </WizardSelect>
                  </div>
                  {creditRows.length > 1 ? (
                    <button
                      type="button"
                      className="rounded-lg border border-neutral-300 px-3 py-2 text-sm dark:border-neutral-700"
                      onClick={() =>
                        setCreditRows((r) => r.filter((_, j) => j !== i))
                      }
                    >
                      Remove
                    </button>
                  ) : null}
                </div>
              ))}
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
                + Add credit
              </button>
            </div>
          </div>

          <div className="rounded-lg border border-neutral-200 dark:border-neutral-700">
            {!royaltySplitOpen ? (
              <div className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="text-sm font-medium text-neutral-900 dark:text-white">
                    Royalty split
                  </p>
                  <p className={`mt-1 text-sm ${HELPER_TEXT}`}>
                    {royaltyCollapsedSummary}
                  </p>
                </div>
                {!metadataLocked ? (
                  <button
                    type="button"
                    className="shrink-0 rounded-lg border border-neutral-300 px-3 py-2 text-sm text-neutral-800 dark:border-neutral-600 dark:text-neutral-100"
                    onClick={() => setRoyaltySplitOpen(true)}
                  >
                    Edit
                  </button>
                ) : (
                  <span
                    className={`shrink-0 text-xs ${HELPER_TEXT}`}
                    title="Royalty splits are locked for ready songs"
                  >
                    Locked
                  </span>
                )}
              </div>
            ) : (
              <div className="border-t border-neutral-200 dark:border-neutral-700">
                <button
                  type="button"
                  className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-medium text-neutral-900 dark:text-white"
                  onClick={() => setRoyaltySplitOpen(false)}
                  aria-expanded={royaltySplitOpen}
                >
                  <span>▲ Royalty split</span>
                  <span className={`text-xs font-normal ${HELPER_TEXT}`}>
                    Total must be 100%
                  </span>
                </button>
                <div className="space-y-3 px-4 pb-4">
                  {royaltySplitInlineError != null && (
                    <p
                      className="text-sm text-red-600 dark:text-red-400"
                      role="alert"
                    >
                      {royaltySplitInlineError}
                    </p>
                  )}
                  {splitRows.map((row, i) => (
                    <RoyaltySplitRow
                      key={i}
                      row={row}
                      canRemove={splitRows.length > 1}
                      locked={metadataLocked}
                      resolvedName={
                        row.artist_id != null
                          ? splitArtistDisplayNames[row.artist_id]
                          : undefined
                      }
                      excludeArtistIds={splitRows
                        .map((r, j) =>
                          j !== i &&
                          r.artist_id != null &&
                          r.artist_id >= 1
                            ? r.artist_id
                            : 0,
                        )
                        .filter((id) => id > 0)}
                      onPickArtist={(artist) => {
                        setSplitArtistDisplayNames((prev) => ({
                          ...prev,
                          [artist.id]: artist.name,
                        }));
                        setSplitRows((rows) => {
                          const next = [...rows];
                          next[i] = {
                            ...next[i],
                            artist_id: artist.id,
                          };
                          return next;
                        });
                        setSplitsEditedByUser(true);
                        setMetadataError(null);
                      }}
                      onClearArtist={() => {
                        setSplitRows((rows) => {
                          const next = [...rows];
                          next[i] = {
                            ...next[i],
                            artist_id: null,
                          };
                          return next;
                        });
                        setSplitsEditedByUser(true);
                        setMetadataError(null);
                      }}
                      onShareChange={(share01) => {
                        setSplitRows((rows) => {
                          const next = [...rows];
                          next[i] = { ...next[i], share: share01 };
                          return next;
                        });
                        setSplitsEditedByUser(true);
                        setMetadataError(null);
                      }}
                      onRemove={() => {
                        setSplitRows((rows) => rows.filter((_, j) => j !== i));
                        setSplitsEditedByUser(true);
                        setMetadataError(null);
                      }}
                    />
                  ))}
                  <button
                    type="button"
                    className="text-sm text-neutral-600 underline dark:text-neutral-400"
                    onClick={() => {
                      setSplitRows((rows) => [
                        ...rows,
                        { artist_id: null, share: 0 },
                      ]);
                      setSplitsEditedByUser(true);
                      setMetadataError(null);
                    }}
                  >
                    + Add collaborator
                  </button>
                </div>
              </div>
            )}
          </div>

          <div className="mt-6 space-y-4 border-t border-neutral-200 pt-6 dark:border-neutral-800">
            <label className="block space-y-1">
              <span className={SECTION_LABEL}>Mood</span>
              <input
                className={WIZARD_INPUT_CLASS}
                value={moodInput}
                onChange={(e) => {
                  setMoodInput(e.target.value);
                  setMetadataError(null);
                }}
                placeholder="melodic, dark, uplifting"
                autoComplete="off"
              />
              <span className={HELPER_TEXT}>
                Comma-separated · max {MAX_MOODS} tags · {MAX_MOOD_LEN} chars
                each
              </span>
            </label>
            <div className="space-y-3">
              <p className="text-sm font-medium text-neutral-900 dark:text-white">
                Location
              </p>
              <label className="block space-y-1">
                <span className={HELPER_TEXT}>Country</span>
                <WizardSelect
                  value={countryCode}
                  onChange={(e) => {
                    setCountryCode(e.target.value);
                    setMetadataError(null);
                  }}
                >
                  <option value="">—</option>
                  {ISO_COUNTRY_OPTIONS.map((c) => (
                    <option key={c.code} value={c.code}>
                      {c.name} ({c.code})
                    </option>
                  ))}
                </WizardSelect>
              </label>
              <label className="block space-y-1">
                <span className={HELPER_TEXT}>City</span>
                <input
                  className={WIZARD_INPUT_CLASS}
                  value={city}
                  maxLength={128}
                  onChange={(e) => {
                    setCity(e.target.value);
                    setMetadataError(null);
                  }}
                  placeholder="e.g. Barcelona"
                  autoComplete="address-level2"
                />
              </label>
            </div>
          </div>

          <button
            type="button"
            disabled={busy || !title.trim() || genreId == null}
            onClick={submitMetadata}
            className={`w-full rounded-lg py-3 text-sm font-medium text-black transition-[background-color,opacity] duration-150 ease-out ${
              busy || !title.trim() || genreId == null
                ? "cursor-not-allowed bg-neutral-200 opacity-75 dark:bg-neutral-600 dark:opacity-80"
                : "cursor-pointer bg-[#F37D25] opacity-100 hover:bg-[#F7A364]"
            }`}
          >
            {busy
              ? isAlbumTrack
                ? "Saving…"
                : songId != null
                  ? "Saving…"
                  : "Creating…"
              : isAlbumTrack
                ? "Save track"
                : songId != null
                  ? "Save & continue"
                  : "Create song & continue"}
          </button>
          {metadataError && metadataError !== "Title is required" && (
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

          <h2 className="text-lg font-medium">
            {isAlbumTrack ? "Album cover" : "Cover art"}
          </h2>
          {isAlbumTrack ? (
            <>
              <p className="text-base text-neutral-700 dark:text-neutral-300">
                This track uses the album cover. Per-track cover upload is
                disabled.
              </p>
              {coverSrc ? (
                <div>
                  <p className="mb-2 text-sm text-neutral-500">Cover</p>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={coverSrc}
                    alt="Album cover"
                    className="max-h-64 w-auto rounded-lg border border-neutral-200 object-contain dark:border-neutral-700"
                  />
                </div>
              ) : (
                <p className="text-sm text-amber-800 dark:text-amber-200">
                  No release cover found. Go back to album setup and upload
                  cover art for this release.
                </p>
              )}
              <input
                type="file"
                accept="image/jpeg,image/png,.jpg,.jpeg,.png"
                disabled
                aria-hidden
                className="block w-full cursor-not-allowed opacity-50 file:mr-4 file:rounded-lg file:border-0 file:bg-neutral-200 file:px-4 file:py-2 dark:file:bg-neutral-800"
              />
              <p className="text-xs text-neutral-500 dark:text-neutral-400">
                Track cover upload is disabled for album tracks.
              </p>
              <button
                type="button"
                disabled={busy || !songId}
                onClick={async () => {
                  if (!songId) return;
                  setBusy(true);
                  try {
                    await refreshSong(songId);
                    setAlbumCoverAdvance(true);
                  } finally {
                    setBusy(false);
                  }
                }}
                className="w-full rounded-lg bg-neutral-900 py-3 text-sm font-medium text-white disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900"
              >
                {busy ? "Working…" : "Continue"}
              </button>
              {song.upload_status !== "ready" && albumCoverAdvance && (
                <p className="text-sm text-neutral-600 dark:text-neutral-400">
                  Finalizing track… this usually takes a few seconds.
                </p>
              )}
            </>
          ) : (
            <>
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
            </>
          )}
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
          {isAlbumTrack ? (
            <button
              type="button"
              onClick={() => onAlbumTrackSaved?.()}
              className="inline-flex w-full items-center justify-center rounded-lg bg-neutral-900 py-3 text-sm font-medium text-white dark:bg-neutral-100 dark:text-neutral-900"
            >
              Back to track list
            </button>
          ) : (
            <Link
              href={`/track/${song.slug}`}
              className="inline-flex w-full items-center justify-center rounded-lg bg-neutral-900 py-3 text-sm font-medium text-white dark:bg-neutral-100 dark:text-neutral-900"
            >
              View song
            </Link>
          )}
          <button
            type="button"
            onClick={clearSession}
            className="w-full text-sm text-neutral-500 underline"
          >
            {isAlbumTrack ? "Discard and reset form" : "Start another upload"}
          </button>
        </section>
      )}
    </UploadWizardPageLayout>
  );
}
