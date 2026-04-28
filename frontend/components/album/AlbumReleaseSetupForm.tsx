"use client";

import { useEffect, useState } from "react";
import { UploadWizardPageLayout } from "@/components/UploadWizardPageLayout";
import { createReleaseDraft, uploadReleaseCover } from "@/lib/api";

type Props = {
  artistId: number;
  headerSlot?: React.ReactNode;
  onComplete: (releaseId: number, title: string) => void;
};

export function AlbumReleaseSetupForm({
  artistId,
  headerSlot,
  onComplete,
}: Props) {
  const [title, setTitle] = useState("");
  const [releaseDate, setReleaseDate] = useState(() => {
    const d = new Date();
    d.setMinutes(d.getMinutes() - 30);
    return d.toISOString().slice(0, 16);
  });
  const [coverFile, setCoverFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [releaseId, setReleaseId] = useState<number | null>(null);
  const [createdTitle, setCreatedTitle] = useState<string>("");
  const [createdReleaseDate, setCreatedReleaseDate] = useState<string>("");
  const [coverPreviewUrl, setCoverPreviewUrl] = useState<string | null>(null);
  const [coverUploadPending, setCoverUploadPending] = useState(false);

  const inConfirmation = releaseId != null && !coverUploadPending;

  useEffect(() => {
    if (coverFile == null) {
      setCoverPreviewUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
      return;
    }
    const nextUrl = URL.createObjectURL(coverFile);
    setCoverPreviewUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return nextUrl;
    });
    return () => {
      URL.revokeObjectURL(nextUrl);
    };
  }, [coverFile]);

  const submitCreateRelease = async () => {
    setError(null);
    if (!title.trim()) {
      setError("Enter an album title.");
      return;
    }
    if (!coverFile) {
      setError("Choose a cover image.");
      return;
    }

    setBusy(true);
    try {
      const iso = new Date(releaseDate).toISOString();
      const created = await createReleaseDraft({
        title: title.trim(),
        artist_id: artistId,
        release_type: "album",
        release_date: iso,
      });
      setReleaseId(created.release_id);
      setCreatedTitle(title.trim());
      setCreatedReleaseDate(releaseDate);
      try {
        await uploadReleaseCover(created.release_id, coverFile);
        setCoverUploadPending(false);
      } catch (e) {
        setCoverUploadPending(true);
        setError(e instanceof Error ? e.message : "Cover upload failed.");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create release.");
    } finally {
      setBusy(false);
    }
  };

  const retryCoverUpload = async () => {
    if (releaseId == null || coverFile == null) return;
    setError(null);
    setBusy(true);
    try {
      await uploadReleaseCover(releaseId, coverFile);
      setCoverUploadPending(false);
    } catch (e) {
      setCoverUploadPending(true);
      setError(e instanceof Error ? e.message : "Cover upload failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <UploadWizardPageLayout>
      {headerSlot}
      <h1 className="mb-2 text-2xl font-semibold tracking-tight">Album setup</h1>
      {!inConfirmation ? (
        <>
          <p className="mb-8 text-sm text-neutral-600 dark:text-neutral-400">
            Set the release details once, then start uploading tracks.
          </p>
          <section className="space-y-6 rounded-xl border border-neutral-200 p-6 dark:border-neutral-800">
            <label className="block space-y-1">
              <span className="text-sm text-neutral-600 dark:text-neutral-400">Album title</span>
              <input
                className="w-full rounded-lg border border-neutral-300 bg-white px-3 py-2 dark:border-neutral-700 dark:bg-neutral-950"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Album title"
              />
            </label>

            <label className="block space-y-1">
              <span className="text-sm text-neutral-600 dark:text-neutral-400">Release date</span>
              <input
                type="datetime-local"
                className="w-full rounded-lg border border-neutral-300 bg-white px-3 py-2 dark:border-neutral-700 dark:bg-neutral-950"
                value={releaseDate}
                onChange={(e) => setReleaseDate(e.target.value)}
              />
            </label>

            <div className="space-y-1">
              <span className="text-sm text-neutral-600 dark:text-neutral-400">Cover art</span>
              <p className="text-xs text-neutral-500 dark:text-neutral-400">
                JPEG or PNG, 1400–3000px.
              </p>
              <input
                type="file"
                accept="image/jpeg,image/png,.jpg,.jpeg,.png"
                disabled={busy}
                className="block w-full text-sm file:mr-4 file:rounded-lg file:border-0 file:bg-neutral-100 file:px-4 file:py-2 dark:file:bg-neutral-800"
                onChange={(e) => {
                  const f = e.target.files?.[0] ?? null;
                  setCoverFile(f);
                  setError(null);
                }}
              />
              {coverPreviewUrl ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={coverPreviewUrl}
                  alt="Selected album cover"
                  className="mt-3 max-h-48 rounded-lg border border-neutral-200 object-contain dark:border-neutral-700"
                />
              ) : null}
            </div>

            <button
              type="button"
              disabled={busy || !title.trim() || !coverFile}
              onClick={() => {
                void submitCreateRelease();
              }}
              className="w-full rounded-lg bg-neutral-900 py-3 text-sm font-medium text-white disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900"
            >
              {busy ? "Creating…" : "Create release"}
            </button>
          </section>
        </>
      ) : (
        <>
          <p className="mb-8 text-sm text-neutral-600 dark:text-neutral-400">
            Release created successfully. You can now start uploading tracks.
          </p>
          <section className="space-y-6 rounded-xl border border-neutral-200 p-6 dark:border-neutral-800">
            <div className="space-y-2">
              <p className="text-sm">
                <span className="text-neutral-500 dark:text-neutral-400">Title:</span>{" "}
                <span className="font-medium text-neutral-900 dark:text-neutral-100">
                  {createdTitle}
                </span>
              </p>
              <p className="text-sm">
                <span className="text-neutral-500 dark:text-neutral-400">Release date:</span>{" "}
                <span className="font-medium text-neutral-900 dark:text-neutral-100">
                  {createdReleaseDate}
                </span>
              </p>
              <p className="text-sm">
                <span className="text-neutral-500 dark:text-neutral-400">Release ID:</span>{" "}
                <span className="font-medium text-neutral-900 dark:text-neutral-100">
                  {releaseId}
                </span>
              </p>
            </div>

            {coverPreviewUrl ? (
              <div>
                <p className="mb-2 text-sm text-neutral-500 dark:text-neutral-400">Cover preview</p>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={coverPreviewUrl}
                  alt="Album cover preview"
                  className="max-h-64 rounded-lg border border-neutral-200 object-contain dark:border-neutral-700"
                />
              </div>
            ) : null}

            <button
              type="button"
              onClick={() => {
                if (releaseId != null) onComplete(releaseId, createdTitle);
              }}
              className="w-full rounded-lg bg-neutral-900 py-3 text-sm font-medium text-white dark:bg-neutral-100 dark:text-neutral-900"
            >
              Upload tracks
            </button>
          </section>
        </>
      )}

      {coverUploadPending ? (
        <section className="mt-4 rounded-xl border border-amber-300 bg-amber-50 p-4 dark:border-amber-900 dark:bg-amber-950/40">
          <p className="text-sm font-medium text-amber-900 dark:text-amber-100">
            Release created, but cover upload failed.
          </p>
          <p className="mt-1 text-sm text-amber-800 dark:text-amber-200">
            Retry cover upload before uploading tracks.
          </p>
          <button
            type="button"
            disabled={busy || releaseId == null || coverFile == null}
            onClick={() => {
              void retryCoverUpload();
            }}
            className="mt-3 rounded-lg border border-amber-400 bg-white px-3 py-2 text-sm font-medium text-amber-900 disabled:opacity-60 dark:border-amber-700 dark:bg-transparent dark:text-amber-100"
          >
            {busy ? "Retrying…" : "Retry cover upload"}
          </button>
        </section>
      ) : null}

      {error ? (
        <p className="mt-4 text-sm text-red-600 dark:text-red-400" role="alert">
          {error}
        </p>
      ) : null}
    </UploadWizardPageLayout>
  );
}
