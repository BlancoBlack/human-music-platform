"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { PlaylistCover } from "@/components/PlaylistCover";
import { useAuth } from "@/context/AuthContext";
import { fetchPlaylistSummaries } from "@/lib/api";

export default function LibraryPlaylistsPage() {
  const { isAuthenticated, authReady } = useAuth();

  const q = useQuery({
    queryKey: ["playlists"],
    queryFn: fetchPlaylistSummaries,
    enabled: authReady && isAuthenticated,
  });

  if (!authReady) {
    return (
      <main className="mx-auto max-w-6xl px-4 py-10">
        <div className="h-8 w-48 animate-pulse rounded bg-neutral-200 dark:bg-neutral-800" />
        <div className="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <div
              key={i}
              className="aspect-square animate-pulse rounded-lg bg-neutral-200 dark:bg-neutral-800"
            />
          ))}
        </div>
      </main>
    );
  }

  if (!isAuthenticated) {
    return (
      <main className="mx-auto max-w-6xl px-4 py-10">
        <h1 className="text-2xl font-semibold tracking-tight text-neutral-900 dark:text-neutral-100">
          Your playlists
        </h1>
        <p className="mt-3 text-neutral-600 dark:text-neutral-400">
          Sign in to view your playlists.
        </p>
        <Link
          href="/login?returnUrl=/library/playlists"
          className="mt-4 inline-block text-sm font-medium text-emerald-600 hover:text-emerald-500 dark:text-emerald-400"
        >
          Log in
        </Link>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-6xl px-4 py-10">
      <h1 className="text-2xl font-semibold tracking-tight text-neutral-900 dark:text-neutral-100">
        Your playlists
      </h1>
      <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
        Open a playlist to continue.
      </p>

      {q.isLoading ? (
        <div className="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="animate-pulse space-y-2">
              <div className="aspect-square rounded-lg bg-neutral-200 dark:bg-neutral-800" />
              <div className="h-4 w-3/4 rounded bg-neutral-200 dark:bg-neutral-800" />
            </div>
          ))}
        </div>
      ) : q.isError ? (
        <p className="mt-8 text-sm text-red-600 dark:text-red-400" role="alert">
          {q.error instanceof Error ? q.error.message : "Could not load playlists."}
        </p>
      ) : !(q.data?.length ?? 0) ? (
        <p className="mt-10 text-center text-sm italic text-neutral-500 dark:text-neutral-400">
          No playlists yet
        </p>
      ) : (
        <ul className="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4">
          {(q.data ?? []).map((p) => (
            <li key={p.id}>
              <Link
                href={`/library/playlists/${p.id}`}
                className="group block rounded-xl transition-all duration-150 ease-out hover:shadow-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-500"
              >
                <div className="relative overflow-hidden rounded-xl">
                  <div className="transition-transform duration-150 ease-out will-change-transform group-hover:scale-[1.03]">
                    <PlaylistCover thumbnails={p.thumbnail_urls} />
                  </div>
                </div>
                <p className="mt-2 truncate text-sm font-medium text-neutral-900 group-hover:text-neutral-700 dark:text-neutral-100 dark:group-hover:text-white">
                  {p.title}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
