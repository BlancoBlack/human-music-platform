"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Image from "next/image";
import { AlbumUploadFlow } from "@/components/album/AlbumUploadFlow";
import { AuthGuard } from "@/components/AuthGuard";
import { StudioLayout } from "@/components/studio/StudioLayout";
import { UploadWizard } from "@/components/UploadWizard";
import { fetchStudioMe } from "@/lib/api";

const UPLOAD_WIZARD_SONG_STORAGE_KEY = "uploadWizardSongId";

function capitalize(value: string): string {
  if (!value) return value;
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function UploadSelector({ onSelect }: { onSelect: (flow: "single" | "album") => void }) {
  return (
    <main className="mx-auto max-w-2xl px-4 py-10">
      <h1 className="mb-2 text-2xl font-semibold tracking-tight">New upload</h1>
      <p className="mb-8 text-sm text-neutral-600 dark:text-neutral-400">
        A single banger or a full album collection?
      </p>

      <div className="grid gap-4 sm:grid-cols-2">
        <button
          type="button"
          onClick={() => onSelect("single")}
          className="rounded-xl border border-neutral-200 bg-white p-6 text-center transition hover:border-neutral-400 dark:border-neutral-800 dark:bg-neutral-950 dark:hover:border-neutral-600"
        >
          <div className="mb-5 flex justify-center">
            <Image
              src="/icons/upload_icon_single.svg"
              alt=""
              aria-hidden
              width={84}
              height={84}
              className="h-[84px] w-[84px] brightness-0 invert"
            />
          </div>
          <span className="block text-lg font-semibold text-neutral-900 dark:text-neutral-100">Single</span>
          <p className="mt-2 text-sm text-neutral-600 dark:text-neutral-400">
            One track with its own cover and metadata.
          </p>
        </button>

        <button
          type="button"
          onClick={() => onSelect("album")}
          className="rounded-xl border border-neutral-200 bg-white p-6 text-center transition hover:border-neutral-400 dark:border-neutral-800 dark:bg-neutral-950 dark:hover:border-neutral-600"
        >
          <div className="mb-5 flex justify-center">
            <Image
              src="/icons/upload_icon_album.svg"
              alt=""
              aria-hidden
              width={84}
              height={84}
              className="h-[84px] w-[84px] brightness-0 invert"
            />
          </div>
          <span className="block text-lg font-semibold text-neutral-900 dark:text-neutral-100">Album</span>
          <p className="mt-2 text-sm text-neutral-600 dark:text-neutral-400">
            Create a release, then add multiple tracks.
          </p>
        </button>
      </div>
    </main>
  );
}

function UploadPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const flow = searchParams.get("flow");
  const flowSingle = flow === "single";
  const flowAlbum = flow === "album";
  const idParam = searchParams.get("id") ?? searchParams.get("song_id") ?? undefined;
  const forceSingleWizard =
    (idParam != null && String(idParam).trim().length > 0) || flowSingle;
  const [resumeSongId, setResumeSongId] = useState<number | null>(null);

  const [loadingArtist, setLoadingArtist] = useState(true);
  const [artistId, setArtistId] = useState<number | null>(null);
  const [artistName, setArtistName] = useState<string>("");
  const [artistError, setArtistError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoadingArtist(true);
    setArtistError(null);

    void fetchStudioMe()
      .then((me) => {
        if (cancelled) return;

        let resolvedArtistId: number | null = null;
        let resolvedArtistName = "";

        if (me.current_context?.type === "artist") {
          resolvedArtistId = Number(me.current_context.id);
          const match = me.allowed_contexts.artists.find(
            (artist) => Number(artist.id) === resolvedArtistId,
          );
          resolvedArtistName = String(match?.name || "").trim();
        }

        if (resolvedArtistId == null && me.allowed_contexts.artists.length > 0) {
          const first = me.allowed_contexts.artists[0];
          resolvedArtistId = Number(first.id);
          resolvedArtistName = String(first.name || "").trim();
        }

        setArtistId(
          resolvedArtistId != null && Number.isFinite(resolvedArtistId) && resolvedArtistId > 0
            ? resolvedArtistId
            : null,
        );
        setArtistName(capitalize(resolvedArtistName));
      })
      .catch((e) => {
        if (cancelled) return;
        setArtistId(null);
        setArtistName("");
        setArtistError(e instanceof Error ? e.message : "Failed to resolve artist context");
      })
      .finally(() => {
        if (!cancelled) setLoadingArtist(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!flowSingle) {
      setResumeSongId(null);
      return;
    }
    if (idParam != null && String(idParam).trim().length > 0) {
      return;
    }
    const raw = window.localStorage.getItem(UPLOAD_WIZARD_SONG_STORAGE_KEY);
    const parsed = raw ? Number.parseInt(raw, 10) : NaN;
    if (Number.isFinite(parsed) && parsed > 0) {
      setResumeSongId(parsed);
      return;
    }
    setResumeSongId(null);
  }, [flowSingle, idParam]);

  const flowHint = useMemo(() => {
    if (artistName) return `Uploading as ${artistName}`;
    if (artistId != null) return `Uploading as artist ${artistId}`;
    return null;
  }, [artistId, artistName]);

  if (loadingArtist) {
    return (
      <main className="mx-auto max-w-2xl px-4 py-10">
        <p className="text-sm text-neutral-500">Loading…</p>
      </main>
    );
  }

  if (artistId == null) {
    return (
      <main className="mx-auto max-w-2xl px-4 py-10">
        <h1 className="text-2xl font-semibold tracking-tight">Upload</h1>
        <p className="mt-3 text-sm text-neutral-600 dark:text-neutral-400">
          No artist context found. Select an artist in Studio context first.
        </p>
        {artistError ? (
          <p className="mt-2 text-sm text-red-600 dark:text-red-400" role="alert">
            {artistError}
          </p>
        ) : null}
      </main>
    );
  }

  if (!forceSingleWizard && !flowAlbum) {
    return (
      <>
        {flowHint ? (
          <div className="mx-auto max-w-2xl px-4 pt-4 text-sm text-neutral-600 dark:text-neutral-400">
            {flowHint}
          </div>
        ) : null}
        <UploadSelector
          onSelect={(nextFlow) => {
            router.push(`/upload?flow=${nextFlow}`);
          }}
        />
      </>
    );
  }

  if (flowAlbum) {
    return (
      <>
        {flowHint ? (
          <div className="mx-auto max-w-2xl px-4 pt-4 text-sm text-neutral-600 dark:text-neutral-400">
            {flowHint}
          </div>
        ) : null}
        <AlbumUploadFlow artistId={artistId} uploadBasePath="/upload" />
      </>
    );
  }

  const showResumePrompt =
    flowSingle &&
    resumeSongId != null &&
    !(idParam != null && String(idParam).trim().length > 0);

  return (
    <UploadWizard
      basePath="/upload"
      suppressStorageResumeRedirect
      fixedArtistId={artistId}
      headerSlot={
        <>
          {flowHint ? (
            <div className="mb-4 text-sm text-neutral-600 dark:text-neutral-400">{flowHint}</div>
          ) : null}
          {showResumePrompt ? (
            <div className="mb-6 rounded-lg border border-neutral-200 bg-neutral-50 p-4 dark:border-neutral-800 dark:bg-neutral-900/40">
              <p className="text-sm font-medium text-neutral-900 dark:text-neutral-100">
                Resume previous upload
              </p>
              <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-400">
                We found a saved single draft (song #{resumeSongId}). Starting a new upload by default.
              </p>
              <div className="mt-3 flex flex-wrap gap-3">
                <button
                  type="button"
                  onClick={() => {
                    router.push(`/upload?flow=single&id=${resumeSongId}`);
                  }}
                  className="rounded-lg border border-neutral-300 px-3 py-2 text-sm font-medium text-neutral-800 dark:border-neutral-600 dark:text-neutral-100"
                >
                  Resume previous upload
                </button>
                <button
                  type="button"
                  onClick={() => {
                    window.localStorage.removeItem(UPLOAD_WIZARD_SONG_STORAGE_KEY);
                    setResumeSongId(null);
                  }}
                  className="rounded-lg bg-neutral-900 px-3 py-2 text-sm font-medium text-white dark:bg-neutral-100 dark:text-neutral-900"
                >
                  Start new upload
                </button>
              </div>
            </div>
          ) : null}
        </>
      }
    />
  );
}

export default function UploadPage() {
  return (
    <Suspense
      fallback={
        <main className="mx-auto max-w-2xl px-4 py-10">
          <p className="text-sm text-neutral-500">Loading…</p>
        </main>
      }
    >
      <StudioLayout>
        <AuthGuard>
          <UploadPageInner />
        </AuthGuard>
      </StudioLayout>
    </Suspense>
  );
}
