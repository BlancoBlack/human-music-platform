"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { fetchArtistBySlug, type ArtistBySlugResponse } from "@/lib/api";

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "not_found" }
  | { kind: "ready"; data: ArtistBySlugResponse };

export default function ArtistSlugPage() {
  const params = useParams();
  const router = useRouter();
  const raw = params.slug;
  const slug = typeof raw === "string" ? raw : Array.isArray(raw) ? (raw[0] ?? "") : "";
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    if (!slug.trim()) return;
    let cancelled = false;
    void fetchArtistBySlug(slug)
      .then((data) => {
        if (cancelled) return;
        if (data.slug !== slug) {
          router.replace(`/artist/${data.slug}`);
          return;
        }
        setState({ kind: "ready", data });
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        const msg = e instanceof Error ? e.message : "Could not load artist.";
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

  if (!slug.trim() || state.kind === "not_found") return <main className="mx-auto max-w-2xl px-4 py-12">Artist not found.</main>;
  if (state.kind === "loading") return <main className="mx-auto max-w-2xl px-4 py-12">Loading artist...</main>;
  if (state.kind === "error") return <main className="mx-auto max-w-2xl px-4 py-12">{state.message}</main>;

  const { data } = state;
  return (
    <main className="mx-auto max-w-2xl px-4 py-10">
      <h1 className="text-2xl font-semibold">{data.name}</h1>
      <p className="mt-2 text-sm text-neutral-500">/{`artist/${data.slug}`}</p>
      <ul className="mt-8 space-y-2">
        {data.songs.map((song) => (
          <li key={song.id}>
            <Link href={`/track/${song.slug}`} className="underline">
              {song.title || "Untitled"}
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
