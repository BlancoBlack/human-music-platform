"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  searchGlobal,
  type GlobalSearchAlbumResult,
  type GlobalSearchArtistResult,
  type GlobalSearchTrackResult,
} from "@/lib/api";

const SEARCH_INPUT_CLASS =
  "rounded-lg border border-solid border-neutral-400 bg-white px-3 py-2 text-sm text-neutral-900 transition-[background-color,border-color,color] duration-150 ease-out dark:border-neutral-600 dark:bg-neutral-950 dark:text-neutral-100 w-full placeholder:text-neutral-400 dark:placeholder:text-neutral-500";

function SearchIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-4 w-4"
      aria-hidden
    >
      <circle cx="11" cy="11" r="7" />
      <path d="m21 21-4.3-4.3" />
    </svg>
  );
}

export function GlobalArtistSearch() {
  const router = useRouter();
  const rootRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const [expanded, setExpanded] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [searchResults, setSearchResults] = useState<{
    artists: GlobalSearchArtistResult[];
    tracks: GlobalSearchTrackResult[];
    albums: GlobalSearchAlbumResult[];
  }>({ artists: [], tracks: [], albums: [] });
  const [searchLoading, setSearchLoading] = useState(false);

  const closeSearch = () => {
    setExpanded(false);
    setSearchOpen(false);
    setQuery("");
    setDebouncedQuery("");
    setSearchResults({ artists: [], tracks: [], albums: [] });
  };

  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedQuery(query), 300);
    return () => window.clearTimeout(t);
  }, [query]);

  useEffect(() => {
    const q = debouncedQuery.trim();
    if (q.length < 2) {
      setSearchResults({ artists: [], tracks: [], albums: [] });
      setSearchLoading(false);
      return;
    }
    let cancelled = false;
    setSearchResults({ artists: [], tracks: [], albums: [] });
    setSearchLoading(true);
    void searchGlobal(q, 10)
      .then((data) => {
        if (!cancelled) {
          setSearchResults({
            artists: data.groups?.artists ?? [],
            tracks: data.groups?.tracks ?? [],
            albums: data.groups?.albums ?? [],
          });
        }
      })
      .catch(() => {
        if (!cancelled) setSearchResults({ artists: [], tracks: [], albums: [] });
      })
      .finally(() => {
        if (!cancelled) setSearchLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [debouncedQuery]);

  useEffect(() => {
    if (!expanded) return;
    const onPointerDown = (event: MouseEvent) => {
      const root = rootRef.current;
      if (!root) return;
      if (root.contains(event.target as Node)) return;
      closeSearch();
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
    };
  }, [expanded]);

  const showSearchPanel =
    expanded && searchOpen && debouncedQuery.trim().length >= 2;

  const hasNoResults = useMemo(
    () =>
      searchResults.artists.length === 0 &&
      searchResults.tracks.length === 0 &&
      searchResults.albums.length === 0,
    [searchResults],
  );

  const openSearch = () => {
    setExpanded(true);
    setSearchOpen(true);
    window.requestAnimationFrame(() => {
      inputRef.current?.focus();
    });
  };

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        className="text-neutral-500 hover:text-neutral-800 dark:text-neutral-400 dark:hover:text-neutral-200"
        aria-label="Search"
        title="Search"
        onClick={openSearch}
      >
        <SearchIcon />
      </button>

      {expanded && (
        <div className="absolute right-0 top-[calc(100%+0.5rem)] z-30 w-[18rem]">
          <input
            ref={inputRef}
            type="search"
            autoComplete="off"
            className={SEARCH_INPUT_CLASS}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setSearchOpen(true);
            }}
            placeholder="Search artist…"
            onFocus={() => setSearchOpen(true)}
            onBlur={() => {
              window.setTimeout(() => setSearchOpen(false), 200);
            }}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                closeSearch();
                return;
              }
              if (e.key === "Enter") {
                e.preventDefault();
                const value = query.trim();
                if (value.length >= 2) {
                  router.push(`/search?q=${encodeURIComponent(value)}`);
                  closeSearch();
                }
              }
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
              {!searchLoading && hasNoResults && (
                <div className="px-3 py-2 text-sm text-neutral-500 dark:text-neutral-400">
                  No results
                </div>
              )}
              {!searchLoading && searchResults.artists.length > 0 && (
                <div className="py-1">
                  <p className="px-3 py-1 text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
                    Artists
                  </p>
                  {searchResults.artists.map((artist) => (
                    <button
                      key={`artist-${artist.id}`}
                      type="button"
                      className="flex w-full px-3 py-2 text-left text-sm text-neutral-800 hover:bg-neutral-100 dark:text-neutral-100 dark:hover:bg-neutral-800"
                      onMouseDown={(e) => e.preventDefault()}
                      onClick={() => {
                        closeSearch();
                        router.push(`/artist/${artist.slug}`);
                      }}
                    >
                      {artist.name}
                    </button>
                  ))}
                </div>
              )}
              {!searchLoading && searchResults.tracks.length > 0 && (
                <div className="py-1">
                  <p className="px-3 py-1 text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
                    Tracks
                  </p>
                  {searchResults.tracks.map((track) => (
                    <button
                      key={`track-${track.id}`}
                      type="button"
                      className="flex w-full flex-col px-3 py-2 text-left text-sm text-neutral-800 hover:bg-neutral-100 dark:text-neutral-100 dark:hover:bg-neutral-800"
                      onMouseDown={(e) => e.preventDefault()}
                      onClick={() => {
                        closeSearch();
                        router.push(`/track/${track.slug}`);
                      }}
                    >
                      <span>{track.title}</span>
                      <span className="text-xs text-neutral-500 dark:text-neutral-400">
                        {track.artist.name}
                      </span>
                    </button>
                  ))}
                </div>
              )}
              {!searchLoading && searchResults.albums.length > 0 && (
                <div className="py-1">
                  <p className="px-3 py-1 text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
                    Albums
                  </p>
                  {searchResults.albums.map((album) => (
                    <button
                      key={`album-${album.id}`}
                      type="button"
                      className="flex w-full px-3 py-2 text-left text-sm text-neutral-800 hover:bg-neutral-100 dark:text-neutral-100 dark:hover:bg-neutral-800"
                      onMouseDown={(e) => e.preventDefault()}
                      onClick={() => {
                        closeSearch();
                        router.push(`/album/${album.slug}`);
                      }}
                    >
                      {album.title}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
