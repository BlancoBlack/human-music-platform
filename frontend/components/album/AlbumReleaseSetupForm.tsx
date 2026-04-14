"use client";

import { useState } from "react";
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
    d.setHours(12, 0, 0, 0);
    return d.toISOString().slice(0, 16);
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [releaseId, setReleaseId] = useState<number | null>(null);
  const [coverUploaded, setCoverUploaded] = useState(false);

  const canContinue = releaseId != null && coverUploaded && title.trim().length > 0;

  const createRelease = async () => {
    setError(null);
    if (!title.trim()) {
      setError("Enter an album title.");
      return;
    }
    setBusy(true);
    try {
      const iso = new Date(releaseDate).toISOString();
      const res = await createReleaseDraft({
        title: title.trim(),
        artist_id: artistId,
        release_type: "album",
        release_date: iso,
      });
      setReleaseId(res.release_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create release.");
    } finally {
      setBusy(false);
    }
  };

  const onCoverFile = async (file: File | null) => {
    setError(null);
    if (!file || releaseId == null) {
      setError(releaseId == null ? "Create the release first, then upload cover." : "Choose a file.");
      return;
    }
    setBusy(true);
    try {
      await uploadReleaseCover(releaseId, file);
      setCoverUploaded(true);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Cover upload failed.";
      setError(msg);
    } finally {
      setBusy(false);
    }
  };

  return (
    <UploadWizardPageLayout>
      {headerSlot}
      <h1 className="mb-2 text-2xl font-semibold tracking-tight">Album setup</h1>
      <p className="mb-8 text-sm text-neutral-600 dark:text-neutral-400">
        Create the release, then upload cover art (required before adding tracks).
      </p>

      <section className="space-y-6 rounded-xl border border-neutral-200 p-6 dark:border-neutral-800">
        <label className="block space-y-1">
          <span className="text-sm text-neutral-600 dark:text-neutral-400">
            Album title
          </span>
          <input
            className="w-full rounded-lg border border-neutral-300 bg-white px-3 py-2 dark:border-neutral-700 dark:bg-neutral-950"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Album title"
          />
        </label>
        <label className="block space-y-1">
          <span className="text-sm text-neutral-600 dark:text-neutral-400">
            Release date
          </span>
          <input
            type="datetime-local"
            className="w-full rounded-lg border border-neutral-300 bg-white px-3 py-2 dark:border-neutral-700 dark:bg-neutral-950"
            value={releaseDate}
            onChange={(e) => setReleaseDate(e.target.value)}
          />
        </label>

        {releaseId == null ? (
          <button
            type="button"
            disabled={busy || !title.trim()}
            onClick={() => void createRelease()}
            className="w-full rounded-lg bg-neutral-900 py-3 text-sm font-medium text-white disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900"
          >
            {busy ? "Creating…" : "Create release"}
          </button>
        ) : (
          <p className="text-sm text-emerald-700 dark:text-emerald-300">
            Release created (ID {releaseId}). Upload cover below.
          </p>
        )}

        <div>
          <span className="mb-2 block text-sm font-medium text-neutral-700 dark:text-neutral-300">
            Cover art (required)
          </span>
          <p className="mb-2 text-xs text-neutral-500 dark:text-neutral-400">
            JPEG or PNG, 1400–3000px (same rules as track covers).
          </p>
          <input
            type="file"
            accept="image/jpeg,image/png,.jpg,.jpeg,.png"
            disabled={busy || releaseId == null}
            className="block w-full text-sm file:mr-4 file:rounded-lg file:border-0 file:bg-neutral-100 file:px-4 file:py-2 dark:file:bg-neutral-800"
            onChange={(e) => {
              const f = e.target.files?.[0] ?? null;
              void onCoverFile(f);
              e.target.value = "";
            }}
          />
          {coverUploaded && (
            <p className="mt-2 text-sm text-emerald-700 dark:text-emerald-300">
              Cover uploaded.
            </p>
          )}
        </div>

        <button
          type="button"
          disabled={!canContinue || busy}
          onClick={() => {
            if (releaseId != null && title.trim()) {
              onComplete(releaseId, title.trim());
            }
          }}
          className="w-full rounded-lg bg-neutral-900 py-3 text-sm font-medium text-white disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900"
        >
          Continue to tracks
        </button>

        {error && (
          <p className="text-sm text-red-600 dark:text-red-400" role="alert">
            {error}
          </p>
        )}
      </section>
    </UploadWizardPageLayout>
  );
}
