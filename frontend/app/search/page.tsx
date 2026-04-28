"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  searchGlobal,
  type GlobalSearchAlbumResult,
  type GlobalSearchArtistResult,
  type GlobalSearchTrackResult,
} from "@/lib/api";

type SearchState = {
  artists: GlobalSearchArtistResult[];
  tracks: GlobalSearchTrackResult[];
  albums: GlobalSearchAlbumResult[];
};

const EMPTY_STATE: SearchState = {
  artists: [],
  tracks: [],
  albums: [],
};

export default function SearchPage() {
  const searchParams = useSearchParams();
  const query = (searchParams.get("q") || "").trim();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<SearchState>(EMPTY_STATE);

  useEffect(() => {
    if (query.length < 2) {
      setData(EMPTY_STATE);
      setError(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    void searchGlobal(query, 20)
      .then((res) => {
        if (cancelled) return;
        setData({
          artists: res.groups?.artists ?? [],
          tracks: res.groups?.tracks ?? [],
          albums: res.groups?.albums ?? [],
        });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof Error ? err.message : "Failed to load search results";
        setError(message);
        setData(EMPTY_STATE);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [query]);

  const isEmpty = useMemo(
    () =>
      data.tracks.length === 0 &&
      data.artists.length === 0 &&
      data.albums.length === 0,
    [data],
  );

  return (
    <main className="mx-auto max-w-2xl px-4 py-10">
      <header className="mb-8 space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">Search</h1>
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          {query ? `Results for "${query}"` : "Type at least 2 characters."}
        </p>
      </header>

      {loading ? (
        <p className="text-sm text-neutral-500 dark:text-neutral-400">
          Searching...
        </p>
      ) : null}

      {error ? (
        <p className="text-sm text-red-600 dark:text-red-400" role="alert">
          {error}
        </p>
      ) : null}

      {!loading && !error && query.length >= 2 && isEmpty ? (
        <p className="text-sm text-neutral-500 dark:text-neutral-400">
          No results for "{query}"
        </p>
      ) : null}

      {!loading && !error && data.tracks.length > 0 ? (
        <section className="mb-10 space-y-2">
          <h2 className="text-lg font-medium text-neutral-900 dark:text-white">
            Tracks
          </h2>
          <ul className="space-y-1">
            {data.tracks.map((track) => (
              <li key={`track-${track.id}`}>
                <Link
                  href={`/track/${track.slug}`}
                  className="block px-1 py-1 text-sm text-neutral-800 hover:text-neutral-950 dark:text-neutral-100 dark:hover:text-white"
                >
                  <span>{track.title}</span>
                  <span className="ml-2 text-neutral-500 dark:text-neutral-400">
                    {track.artist.name}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {!loading && !error && data.artists.length > 0 ? (
        <section className="mb-10 space-y-2">
          <h2 className="text-lg font-medium text-neutral-900 dark:text-white">
            Artists
          </h2>
          <ul className="space-y-1">
            {data.artists.map((artist) => (
              <li key={`artist-${artist.id}`}>
                <Link
                  href={`/artist/${artist.slug}`}
                  className="block px-1 py-1 text-sm text-neutral-800 hover:text-neutral-950 dark:text-neutral-100 dark:hover:text-white"
                >
                  {artist.name}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {!loading && !error && data.albums.length > 0 ? (
        <section className="space-y-2">
          <h2 className="text-lg font-medium text-neutral-900 dark:text-white">
            Albums
          </h2>
          <ul className="space-y-1">
            {data.albums.map((album) => (
              <li key={`album-${album.id}`}>
                <Link
                  href={`/album/${album.slug}`}
                  className="block px-1 py-1 text-sm text-neutral-800 hover:text-neutral-950 dark:text-neutral-100 dark:hover:text-white"
                >
                  {album.title}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </main>
  );
}
