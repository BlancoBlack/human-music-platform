"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { fetchAlbumBySlug, type AlbumBySlugResponse } from "@/lib/api";

type State =
  | { kind: "loading" }
  | { kind: "not_found" }
  | { kind: "error"; message: string }
  | { kind: "ready"; data: AlbumBySlugResponse };

export default function AlbumSlugPage() {
  const params = useParams();
  const router = useRouter();
  const raw = params.slug;
  const slug = typeof raw === "string" ? raw : Array.isArray(raw) ? (raw[0] ?? "") : "";
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    if (!slug.trim()) return;
    let cancelled = false;
    setState({ kind: "loading" });
    void fetchAlbumBySlug(slug)
      .then((data) => {
        if (cancelled) return;
        if (data.slug !== slug) {
          router.replace(`/album/${data.slug}`);
          return;
        }
        setState({ kind: "ready", data });
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        const msg = e instanceof Error ? e.message : "Could not load album.";
        if (msg.toLowerCase().includes("not found")) {
          setState({ kind: "not_found" });
          return;
        }
        setState({ kind: "error", message: msg });
      });
    return () => {
      cancelled = true;
    };
  }, [slug, router]);

  if (!slug.trim() || state.kind === "not_found") return <main className="mx-auto max-w-2xl px-4 py-12">Album not found.</main>;
  if (state.kind === "loading") return <main className="mx-auto max-w-2xl px-4 py-12">Loading album...</main>;
  if (state.kind === "error") return <main className="mx-auto max-w-2xl px-4 py-12">{state.message}</main>;

  const { data } = state;
  return (
    <main className="mx-auto max-w-2xl px-4 py-10">
      <div className="mb-4 text-sm text-neutral-600 dark:text-neutral-400">
        <Link href={`/artist/${data.artist.slug}`} className="underline">
          {data.artist.name}
        </Link>
      </div>
      <h1 className="text-2xl font-semibold">{data.title}</h1>
      <p className="mt-2 text-sm text-neutral-500">/{`album/${data.slug}`}</p>
      <ul className="mt-8 space-y-2">
        {data.tracks.map((track) => (
          <li key={track.id}>
            <Link href={`/track/${track.slug}`} className="underline">
              {track.title || "Untitled"}
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
