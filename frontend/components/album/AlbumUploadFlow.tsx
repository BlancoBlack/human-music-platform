"use client";

import { useCallback, useState } from "react";
import Link from "next/link";
import { UploadWizard } from "@/components/UploadWizard";
import {
  UPLOAD_WIZARD_PAGE_SHELL_CLASS,
  UploadWizardPageLayout,
} from "@/components/UploadWizardPageLayout";
import { AlbumReleaseSetupForm } from "./AlbumReleaseSetupForm";
import { AlbumTrackList } from "./AlbumTrackList";

export type AlbumFlowStep = "setup" | "tracks" | "editor";

type EditorContext = {
  songId: number | null;
  trackIndex: number;
  trackCount: number;
};

type Props = {
  artistId: number;
};

export function AlbumUploadFlow({ artistId }: Props) {
  const [step, setStep] = useState<AlbumFlowStep>("setup");
  const [releaseId, setReleaseId] = useState<number | null>(null);
  const [releaseTitle, setReleaseTitle] = useState("");
  const [editor, setEditor] = useState<EditorContext | null>(null);

  const header = (
    <div className="mb-8 flex flex-wrap items-center gap-3">
      <Link
        href={`/artist-upload?artist_id=${artistId}`}
        className="text-sm text-neutral-600 underline-offset-2 hover:underline dark:text-neutral-400"
      >
        ← Back to upload type
      </Link>
    </div>
  );

  const onSetupComplete = useCallback((id: number, title: string) => {
    setReleaseId(id);
    setReleaseTitle(title);
    setStep("tracks");
  }, []);

  if (step === "setup") {
    return (
      <AlbumReleaseSetupForm
        artistId={artistId}
        headerSlot={header}
        onComplete={onSetupComplete}
      />
    );
  }

  if (step === "tracks" && releaseId != null) {
    return (
      <AlbumTrackList
        releaseId={releaseId}
        releaseTitle={releaseTitle}
        headerSlot={header}
        onAddTrack={({ trackIndex, trackCount }) => {
          setEditor({
            songId: null,
            trackIndex,
            trackCount,
          });
          setStep("editor");
        }}
        onEditTrack={({ songId, trackIndex, trackCount }) => {
          setEditor({
            songId,
            trackIndex,
            trackCount,
          });
          setStep("editor");
        }}
      />
    );
  }

  if (step === "editor" && releaseId != null && editor != null) {
    return (
      <div className="min-h-screen bg-neutral-50 dark:bg-neutral-950">
        <div className={`${UPLOAD_WIZARD_PAGE_SHELL_CLASS} pt-6`}>
          <button
            type="button"
            className="text-sm text-neutral-600 underline-offset-2 hover:underline dark:text-neutral-400"
            onClick={() => {
              setEditor(null);
              setStep("tracks");
            }}
          >
            ← Back to track list
          </button>
        </div>
        <UploadWizard
          key={`${releaseId}-${editor.songId ?? "new"}-${editor.trackIndex}`}
          mode="album-track"
          fixedArtistId={artistId}
          suppressStorageResumeRedirect
          releaseId={releaseId}
          albumTitle={releaseTitle}
          trackIndex={editor.trackIndex}
          trackCount={editor.trackCount}
          initialSongId={editor.songId}
          onAlbumTrackSaved={() => {
            setEditor(null);
            setStep("tracks");
          }}
        />
      </div>
    );
  }

  return (
    <UploadWizardPageLayout>
      {header}
      <p className="text-sm text-red-600">Something went wrong. Start over.</p>
      <Link href="/artist-upload" className="mt-4 inline-block text-sm underline">
        Artist upload
      </Link>
    </UploadWizardPageLayout>
  );
}
