"use client";

import Link from "next/link";
import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { AuthGuard } from "@/components/AuthGuard";
import { API_BASE } from "@/lib/publicEnv";

function ArtistAnalyticsInner() {
  const searchParams = useSearchParams();
  const raw = searchParams.get("artist_id");
  const aid = raw ? parseInt(raw, 10) : NaN;
  const valid = Number.isFinite(aid) && aid > 0;
  const apiUrl = valid ? `${API_BASE}/artist-analytics/${aid}` : null;

  if (!valid) {
    return (
      <main className="mx-auto max-w-xl px-4 py-12">
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          Add <code className="font-mono">artist_id</code> to the query string,
          e.g.{" "}
          <Link href="/artist-analytics?artist_id=1" className="underline">
            /artist-analytics?artist_id=1
          </Link>
          .
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-xl px-4 py-12">
      <h1 className="text-xl font-semibold text-neutral-900 dark:text-neutral-100">
        Analytics
      </h1>
      <p className="mt-3 text-sm text-neutral-600 dark:text-neutral-400">
        The detailed analytics UI is served by the API. You are signed in to
        the app; open the dashboard in a new tab when you are ready.
      </p>
      <p className="mt-6">
        <a
          href={apiUrl!}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-200"
        >
          Open API analytics (artist {aid})
        </a>
      </p>
    </main>
  );
}

export default function ArtistAnalyticsPage() {
  return (
    <Suspense
      fallback={
        <main className="mx-auto max-w-xl px-4 py-12 text-sm text-neutral-500">
          Loading…
        </main>
      }
    >
      <AuthGuard>
        <ArtistAnalyticsInner />
      </AuthGuard>
    </Suspense>
  );
}
