"use client";

import { API_BASE } from "@/lib/publicEnv";

/**
 * Playlist artwork: up to four thumbnail URLs in a 2×2 collage, or gradient placeholder.
 * Relative paths (API ``/media/…``, ``/uploads/…``) are prefixed with ``NEXT_PUBLIC_API_BASE``,
 * matching playlist detail and discovery rows. Absolute ``http(s)`` URLs are unchanged.
 * URLs are deduped (first-seen order); if fewer than four unique, slots repeat unique URLs to fill the grid.
 */

function resolveThumbnailSrc(raw: string): string {
  const s = String(raw).trim();
  if (!s) return "";
  if (/^https?:\/\//i.test(s)) return s;
  return `${API_BASE}${s.startsWith("/") ? s : `/${s}`}`;
}

function collageSlots(thumbnails: string[] | undefined): string[] {
  const inputs = (thumbnails ?? [])
    .map((s) => resolveThumbnailSrc(String(s)))
    .filter(Boolean);
  const seen = new Set<string>();
  const unique: string[] = [];
  for (const u of inputs) {
    if (seen.has(u)) continue;
    seen.add(u);
    unique.push(u);
    if (unique.length >= 4) break;
  }
  if (unique.length === 0) return [];
  const out = [...unique];
  let i = 0;
  while (out.length < 4) {
    out.push(unique[i % unique.length]!);
    i += 1;
  }
  return out;
}

export function PlaylistCover({
  thumbnails,
  className = "",
}: {
  thumbnails?: string[];
  className?: string;
}) {
  const slots = collageSlots(thumbnails);
  const hasCollage = slots.length > 0;

  return (
    <div
      className={`relative aspect-square w-full overflow-hidden rounded-xl bg-neutral-900 shadow-lg ring-1 ring-black/15 transition-shadow duration-200 dark:ring-white/10 ${className}`}
    >
      {hasCollage ? (
        <div className="grid h-full grid-cols-2 grid-rows-2 gap-1 bg-neutral-950 p-1">
          {[0, 1, 2, 3].map((i) => (
            <div
              key={i}
              className="relative min-h-0 overflow-hidden rounded-md bg-neutral-800"
            >
              {slots[i] ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={slots[i]}
                  alt=""
                  className="h-full w-full object-cover"
                  draggable={false}
                />
              ) : null}
            </div>
          ))}
        </div>
      ) : (
        <div
          className="flex h-full w-full flex-col items-center justify-center bg-gradient-to-br from-violet-950/90 via-neutral-900 to-neutral-950 shadow-inner"
          aria-hidden
        >
          <div className="rounded-full bg-white/5 p-3 shadow-md ring-1 ring-white/10">
            <svg
              className="h-9 w-9 text-neutral-400/90"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={1.25}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="m9 18V5l12-2v13M9 18c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-13c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-2"
              />
            </svg>
          </div>
        </div>
      )}
    </div>
  );
}
