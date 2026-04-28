"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AlbumUploadFlow } from "@/components/album/AlbumUploadFlow";
import { ArtistHubNav } from "@/components/ArtistHubNav";
import { AuthGuard } from "@/components/AuthGuard";
import { UploadWizard } from "@/components/UploadWizard";
import {
  API_BASE,
  ApiNotFoundError,
  deleteSong,
  fetchArtist,
  fetchSong,
} from "@/lib/api";

const UPLOAD_WIZARD_SONG_STORAGE_KEY = "uploadWizardSongId";

function ArtistUploadInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const raw = searchParams.get("artist_id");
  const aid = raw ? parseInt(raw, 10) : NaN;
  const artistValid = Number.isFinite(aid) && aid > 0;
  const flow = searchParams.get("flow");
  const flowSingle = flow === "single";
  const flowAlbum = flow === "album";
  const idParam =
    searchParams.get("id") ?? searchParams.get("song_id") ?? undefined;
  const hasIdInUrl =
    idParam != null && String(idParam).trim() !== "";
  const forceSingleWizard = hasIdInUrl || flowSingle;

  const [resumeSongId, setResumeSongId] = useState<number | null>(() => {
    if (typeof window === "undefined") return null;
    const rawLs = localStorage.getItem(UPLOAD_WIZARD_SONG_STORAGE_KEY);
    const sid = rawLs ? parseInt(rawLs, 10) : NaN;
    return Number.isFinite(sid) && sid > 0 ? sid : null;
  });
  const [resumeUploadStatus, setResumeUploadStatus] = useState<string | null>(
    null,
  );
  const [headerArtistName, setHeaderArtistName] = useState<string | null>(null);
  const [startNewError, setStartNewError] = useState<string | null>(null);
  const [startNewBusy, setStartNewBusy] = useState(false);
  const hasResumeState = !hasIdInUrl && resumeSongId != null;

  useEffect(() => {
    if (!artistValid) return;
    let cancelled = false;
    void fetchArtist(aid)
      .then((artist) => {
        if (!cancelled) setHeaderArtistName(artist.name);
      })
      .catch(() => {
        if (!cancelled) setHeaderArtistName(null);
      });
    return () => {
      cancelled = true;
    };
  }, [artistValid, aid]);

  useEffect(() => {
    if (!hasResumeState || resumeSongId == null) return;
    let cancelled = false;
    void fetchSong(resumeSongId)
      .then((song) => {
        if (!cancelled) setResumeUploadStatus(song.upload_status);
      })
      .catch((e) => {
        if (cancelled) return;
        if (e instanceof ApiNotFoundError) {
          localStorage.removeItem(UPLOAD_WIZARD_SONG_STORAGE_KEY);
          setResumeSongId(null);
          setResumeUploadStatus(null);
          return;
        }
        setResumeUploadStatus("");
      });
    return () => {
      cancelled = true;
    };
  }, [hasResumeState, resumeSongId]);

  const attemptDeleteAndRestart = () => {
    if (resumeSongId == null) return;
    setStartNewError(null);
    setStartNewBusy(true);
    void deleteSong(resumeSongId)
      .then(() => {
        localStorage.removeItem(UPLOAD_WIZARD_SONG_STORAGE_KEY);
        router.replace(`/artist-upload?artist_id=${aid}`);
      })
      .catch((e) => {
        setStartNewError(
          e instanceof Error ? e.message : "Could not delete the song. Try again.",
        );
      })
      .finally(() => {
        setStartNewBusy(false);
      });
  };

  if (!artistValid) {
    return (
      <main className="mx-auto max-w-2xl px-4 py-10">
        <h1 className="text-xl font-semibold tracking-tight">Upload</h1>
        <div
          className="mt-6 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-100"
          role="alert"
        >
          <p className="font-medium">Missing artist</p>
          <p className="mt-2 text-amber-900/90 dark:text-amber-100/90">
            Add a valid <code className="rounded bg-amber-100/80 px-1 dark:bg-amber-900/50">artist_id</code> to the URL (e.g.{" "}
            <code className="rounded bg-amber-100/80 px-1 dark:bg-amber-900/50">
              ?artist_id=1
            </code>
            ), or open{" "}
            <strong>Upload</strong> from your artist overview.
          </p>
          <p className="mt-3">
            <a
              href={API_BASE}
              className="text-amber-900 underline dark:text-amber-200"
            >
              API home
            </a>
            <span className="text-amber-900/70 dark:text-amber-200/70">
              {" "}
              — use the Upload link in your artist overview when you know your
              artist ID.
            </span>
          </p>
        </div>
      </main>
    );
  }

  if (!forceSingleWizard && !flowAlbum) {
    return (
      <main className="mx-auto max-w-2xl px-4 py-10">
        <ArtistHubNav artistId={aid} active="upload" />
        <div
          className="mt-3 mb-8 text-sm text-neutral-600 dark:text-neutral-400"
          aria-live="polite"
        >
          <p>
            Uploading as:{" "}
            {headerArtistName != null ? (
              <span className="font-medium text-neutral-800 dark:text-neutral-200">
                {headerArtistName}
              </span>
            ) : (
              <>
                Artist{" "}
                <span className="font-mono font-medium tabular-nums text-neutral-800 dark:text-neutral-200">
                  {aid}
                </span>
              </>
            )}
          </p>
        </div>
        <h1 className="mb-2 text-2xl font-semibold tracking-tight">New upload</h1>
        <p className="mb-8 text-sm text-neutral-600 dark:text-neutral-400">
          Choose whether you are uploading a standalone single or an album.
        </p>
        <div className="grid gap-4 sm:grid-cols-2">
          <button
            type="button"
            className="rounded-xl border border-neutral-200 bg-white p-6 text-left shadow-sm transition hover:border-neutral-400 dark:border-neutral-800 dark:bg-neutral-950 dark:hover:border-neutral-600"
            onClick={() => {
              router.push(`/artist-upload?artist_id=${aid}&flow=single`);
            }}
          >
            <span className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
              Single
            </span>
            <p className="mt-2 text-sm text-neutral-600 dark:text-neutral-400">
              One track with its own cover and metadata (existing upload flow).
            </p>
          </button>
          <button
            type="button"
            className="rounded-xl border border-neutral-200 bg-white p-6 text-left shadow-sm transition hover:border-neutral-400 dark:border-neutral-800 dark:bg-neutral-950 dark:hover:border-neutral-600"
            onClick={() => {
              router.push(`/artist-upload?artist_id=${aid}&flow=album`);
            }}
          >
            <span className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
              Album
            </span>
            <p className="mt-2 text-sm text-neutral-600 dark:text-neutral-400">
              Create a release, one cover for all tracks, then add each track.
            </p>
          </button>
        </div>
      </main>
    );
  }

  if (flowAlbum) {
    return (
      <>
        <ArtistHubNav artistId={aid} active="upload" />
        <div
          className="mx-auto max-w-2xl px-4 pt-3 text-sm text-neutral-600 dark:text-neutral-400"
          aria-live="polite"
        >
          <p>
            Uploading as:{" "}
            {headerArtistName != null ? (
              <span className="font-medium text-neutral-800 dark:text-neutral-200">
                {headerArtistName}
              </span>
            ) : (
              <span className="font-mono font-medium tabular-nums text-neutral-800 dark:text-neutral-200">
                {aid}
              </span>
            )}
          </p>
        </div>
        <AlbumUploadFlow artistId={aid} />
      </>
    );
  }

  if (hasResumeState) {
    return (
      <>
        <ArtistHubNav artistId={aid} active="upload" />
        <div
          className="mx-auto max-w-2xl px-4 pt-3 text-sm text-neutral-600 dark:text-neutral-400"
          aria-live="polite"
        >
          <p>
            Uploading as:{" "}
            {headerArtistName != null ? (
              <span className="font-medium text-neutral-800 dark:text-neutral-200">
                {headerArtistName}
              </span>
            ) : (
              <>
                Artist{" "}
                <span className="font-mono font-medium tabular-nums text-neutral-800 dark:text-neutral-200">
                  {aid}
                </span>
              </>
            )}
          </p>
          {headerArtistName != null && (
            <p className="mt-0.5 text-xs text-neutral-500 dark:text-neutral-500">
              (ID {aid})
            </p>
          )}
        </div>
        <div
          className="mx-auto max-w-2xl px-4 pt-6"
          role="region"
          aria-label="Resume previous upload"
        >
          <div className="mb-6 rounded-xl border border-neutral-200 bg-neutral-50 p-4 dark:border-neutral-800 dark:bg-neutral-900/40">
            <h2 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">
              Continue your last upload
            </h2>
            <p className="mt-2 text-sm text-neutral-600 dark:text-neutral-400">
              Song ID:{" "}
              <span className="font-mono tabular-nums text-neutral-900 dark:text-neutral-100">
                {resumeSongId}
              </span>
            </p>
            {resumeUploadStatus != null && (
              <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-400">
                Status:{" "}
                <span className="font-medium text-neutral-800 dark:text-neutral-200">
                  {resumeUploadStatus}
                </span>
              </p>
            )}
            {startNewError != null && (
              <div
                className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/40 dark:text-red-100"
                role="alert"
              >
                <p>Delete failed. Retry or continue editing existing draft.</p>
                <p className="mt-1 text-xs opacity-80">{startNewError}</p>
              </div>
            )}
            <div className="mt-4 flex flex-wrap gap-3">
              <button
                type="button"
                className="rounded-lg bg-neutral-900 px-4 py-2 text-sm font-medium text-white dark:bg-neutral-100 dark:text-neutral-900"
                onClick={() => {
                  router.push(`/artist-upload?artist_id=${aid}&id=${resumeSongId}`);
                }}
              >
                Continue upload
              </button>
              <button
                type="button"
                disabled={startNewBusy}
                className="rounded-lg border border-neutral-300 bg-white px-4 py-2 text-sm font-medium text-neutral-800 disabled:opacity-60 dark:border-neutral-600 dark:bg-neutral-950 dark:text-neutral-100"
                onClick={attemptDeleteAndRestart}
              >
                {startNewBusy
                  ? "Deleting…"
                  : startNewError != null
                    ? "Retry delete"
                    : "Start new"}
              </button>
            </div>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <UploadWizard
        basePath="/artist-upload"
        fixedArtistId={aid}
        suppressStorageResumeRedirect
        headerSlot={
          <>
            <ArtistHubNav artistId={aid} active="upload" />
            <div
              className="mt-3 mb-6 text-sm text-neutral-600 dark:text-neutral-400"
              aria-live="polite"
            >
              <p>
                Uploading as:{" "}
                {headerArtistName != null ? (
                  <span className="font-medium text-neutral-800 dark:text-neutral-200">
                    {headerArtistName}
                  </span>
                ) : (
                  <>
                    Artist{" "}
                    <span className="font-mono font-medium tabular-nums text-neutral-800 dark:text-neutral-200">
                      {aid}
                    </span>
                  </>
                )}
              </p>
              {headerArtistName != null && (
                <p className="mt-0.5 text-xs text-neutral-500 dark:text-neutral-500">
                  (ID {aid})
                </p>
              )}
            </div>
          </>
        }
      />
    </>
  );
}

export default function ArtistUploadPage() {
  return (
    <Suspense
      fallback={
        <main className="mx-auto max-w-2xl px-4 py-10">
          <p className="text-sm text-neutral-500">Loading…</p>
        </main>
      }
    >
      <AuthGuard>
        <ArtistUploadInner />
      </AuthGuard>
    </Suspense>
  );
}
