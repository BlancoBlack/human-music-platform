"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArtistHubNav } from "@/components/ArtistHubNav";
import { AuthGuard } from "@/components/AuthGuard";
import { UploadWizard } from "@/components/UploadWizard";
import { API_BASE, fetchArtist, fetchSong } from "@/lib/api";

const UPLOAD_WIZARD_SONG_STORAGE_KEY = "uploadWizardSongId";

function ArtistUploadInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const raw = searchParams.get("artist_id");
  const aid = raw ? parseInt(raw, 10) : NaN;
  const artistValid = Number.isFinite(aid) && aid > 0;
  const idParam = searchParams.get("id");
  const hasIdInUrl = idParam != null && idParam.trim() !== "";

  const [showResumePrompt, setShowResumePrompt] = useState(false);
  const [resumeSongId, setResumeSongId] = useState<number | null>(null);
  const [resumeUploadStatus, setResumeUploadStatus] = useState<string | null>(
    null,
  );
  const [headerArtistName, setHeaderArtistName] = useState<string | null>(null);

  useEffect(() => {
    if (!artistValid) {
      setHeaderArtistName(null);
      return;
    }
    setHeaderArtistName(null);
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
    if (!artistValid) {
      setShowResumePrompt(false);
      setResumeSongId(null);
      return;
    }
    if (hasIdInUrl) {
      setShowResumePrompt(false);
      return;
    }
    const rawLs = localStorage.getItem(UPLOAD_WIZARD_SONG_STORAGE_KEY);
    const sid = rawLs ? parseInt(rawLs, 10) : NaN;
    if (Number.isFinite(sid) && sid > 0) {
      setResumeSongId(sid);
      setShowResumePrompt(true);
    } else {
      setResumeSongId(null);
      setShowResumePrompt(false);
    }
  }, [artistValid, hasIdInUrl]);

  useEffect(() => {
    if (!showResumePrompt || resumeSongId == null) {
      setResumeUploadStatus(null);
      return;
    }
    let cancelled = false;
    setResumeUploadStatus(null);
    void fetchSong(resumeSongId)
      .then((song) => {
        if (!cancelled) setResumeUploadStatus(song.upload_status);
      })
      .catch(() => {
        if (!cancelled) setResumeUploadStatus(null);
      });
    return () => {
      cancelled = true;
    };
  }, [showResumePrompt, resumeSongId]);

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

  return (
    <>
      {showResumePrompt && resumeSongId != null && (
        <div
          className="mx-auto max-w-2xl px-4 pt-10"
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
            <div className="mt-4 flex flex-wrap gap-3">
              <button
                type="button"
                className="rounded-lg bg-neutral-900 px-4 py-2 text-sm font-medium text-white dark:bg-neutral-100 dark:text-neutral-900"
                onClick={() => {
                  router.push(
                    `/artist-upload?artist_id=${aid}&id=${resumeSongId}`,
                  );
                }}
              >
                Continue
              </button>
              <button
                type="button"
                className="rounded-lg border border-neutral-300 bg-white px-4 py-2 text-sm font-medium text-neutral-800 dark:border-neutral-600 dark:bg-neutral-950 dark:text-neutral-100"
                onClick={() => {
                  localStorage.removeItem(UPLOAD_WIZARD_SONG_STORAGE_KEY);
                  window.location.href = `/artist-upload?artist_id=${aid}`;
                }}
              >
                Start new
              </button>
            </div>
          </div>
        </div>
      )}
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
