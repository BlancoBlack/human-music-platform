"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";
import { useAudioPlayer } from "@/components/audio/AudioPlayerProvider";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/context/ToastContext";
import {
  addTrackToPlaylist,
  createPlaylist,
  fetchPlaylistSummaries,
  type PlaylistSummary,
} from "@/lib/api";

function isDuplicatePlaylistError(error: unknown): boolean {
  const msg = error instanceof Error ? error.message : String(error);
  return /already in playlist/i.test(msg);
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message.trim()
    ? error.message.trim()
    : fallback;
}

export function PlaylistModal({
  songId,
  open,
  onClose,
}: {
  songId: number;
  open: boolean;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const { suppressNextClicks } = useAudioPlayer();
  const { isAuthenticated, authReady } = useAuth();
  const { showSuccess, showError } = useToast();

  const closeModal = useCallback(() => {
    suppressNextClicks(250);
    onClose();
  }, [onClose, suppressNextClicks]);
  const [submittingPlaylistId, setSubmittingPlaylistId] = useState<
    number | null
  >(null);
  const [creatingInline, setCreatingInline] = useState(false);
  const [newPlaylistTitle, setNewPlaylistTitle] = useState("");
  const [creatingSubmitting, setCreatingSubmitting] = useState(false);

  const q = useQuery({
    queryKey: ["playlists"],
    queryFn: fetchPlaylistSummaries,
    enabled: open && authReady && isAuthenticated,
  });

  useEffect(() => {
    if (!open) {
      setCreatingInline(false);
      setNewPlaylistTitle("");
      setCreatingSubmitting(false);
    }
  }, [open]);

  const busyExisting = submittingPlaylistId !== null;
  const busyCreate = creatingSubmitting;
  const listLocked = busyExisting || busyCreate;

  const handlePick = async (playlistId: number, playlistTitle: string) => {
    if (listLocked) return;
    setSubmittingPlaylistId(playlistId);
    try {
      await addTrackToPlaylist(playlistId, songId);
      showSuccess(`Added to ${playlistTitle}`, {
        action: {
          label: "View",
          href: `/library/playlists/${playlistId}`,
        },
      });
      closeModal();
    } catch (e) {
      console.error("[playlist modal] add to playlist failed", e);
      showError(
        isDuplicatePlaylistError(e)
          ? "Already in playlist"
          : "Could not add to playlist",
      );
    } finally {
      setSubmittingPlaylistId(null);
    }
  };

  const handleCreateConfirm = async () => {
    const trimmed = newPlaylistTitle.trim();
    if (!trimmed || listLocked) return;
    setCreatingSubmitting(true);
    let createdId: number;
    let createdTitle: string;
    try {
      const created = await createPlaylist(trimmed);
      createdId = created.id;
      createdTitle = created.title;
    } catch (e) {
      console.error("[playlist modal] create playlist failed", e);
      showError(errorMessage(e, "Could not create playlist"));
      setCreatingSubmitting(false);
      return;
    }
    try {
      await addTrackToPlaylist(createdId, songId);
    } catch (e) {
      console.error("[playlist modal] add after create failed", e);
      showError(
        isDuplicatePlaylistError(e)
          ? "Already in playlist"
          : "Could not add to playlist",
      );
      void queryClient.invalidateQueries({ queryKey: ["playlists"] });
      setCreatingSubmitting(false);
      setCreatingInline(false);
      setNewPlaylistTitle("");
      return;
    }
    void queryClient.invalidateQueries({ queryKey: ["playlists"] });
    showSuccess(`Added to ${createdTitle}`, {
      action: {
        label: "View",
        href: `/library/playlists/${createdId}`,
      },
    });
    setCreatingSubmitting(false);
    closeModal();
  };

  const cancelInlineCreate = () => {
    if (busyCreate) return;
    setCreatingInline(false);
    setNewPlaylistTitle("");
  };

  const playlists = q.data ?? [];
  const hasPlaylists = playlists.length > 0;
  const trimmedNewTitle = newPlaylistTitle.trim();
  const confirmCreateDisabled =
    !trimmedNewTitle || listLocked || busyCreate;

  if (!open) return null;

  const inlineCreateForm = creatingInline ? (
    <form
      className="border-t border-white/10 px-4 py-3"
      onSubmit={(e) => {
        e.preventDefault();
        void handleCreateConfirm();
      }}
    >
      <label htmlFor="playlist-modal-new-title" className="sr-only">
        Playlist name
      </label>
      <input
        id="playlist-modal-new-title"
        type="text"
        value={newPlaylistTitle}
        onChange={(e) => setNewPlaylistTitle(e.target.value)}
        placeholder="Playlist name"
        readOnly={listLocked}
        autoFocus
        autoComplete="off"
        className={`w-full rounded-lg border border-white/15 bg-neutral-900 px-3 py-2 text-sm text-neutral-100 placeholder:text-neutral-600 outline-none ring-emerald-500/40 focus:border-emerald-500/50 focus:ring-2 ${
          listLocked ? "cursor-wait opacity-60" : ""
        }`}
      />
      <div className="mt-3 flex gap-2">
        <button
          type="button"
          disabled={busyCreate}
          className="flex-1 rounded-lg border border-white/15 py-2 text-sm font-medium text-neutral-300 transition hover:bg-white/5 active:bg-white/10 disabled:opacity-50"
          onClick={cancelInlineCreate}
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={confirmCreateDisabled}
          className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-emerald-600/90 py-2 text-sm font-semibold text-white transition hover:bg-emerald-600 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busyCreate ? (
            <span
              className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white/80 border-t-transparent"
              aria-hidden
            />
          ) : null}
          Confirm
        </button>
      </div>
    </form>
  ) : null;

  return (
    <div
      className="fixed inset-0 z-[60] flex items-end justify-center bg-black/60 px-3 py-6 sm:items-center"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) {
          e.preventDefault();
        }
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          closeModal();
        }
      }}
    >
      <div
        className="flex max-h-[min(70vh,520px)] w-full max-w-md flex-col overflow-hidden rounded-t-2xl border border-white/15 bg-neutral-950 shadow-xl dark:bg-neutral-950 sm:rounded-2xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="playlist-modal-title"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => {
          if (e.key === " ") e.stopPropagation();
          if (e.key === "Escape") {
            e.preventDefault();
            closeModal();
          }
        }}
      >
        <div className="border-b border-white/10 px-4 py-3">
          <h2
            id="playlist-modal-title"
            className="text-base font-semibold text-neutral-100"
          >
            Add to playlist
          </h2>
          <p className="mt-1 text-xs text-neutral-500">
            Choose a playlist you own
          </p>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          {q.isLoading && (
            <p className="px-4 py-6 text-sm text-neutral-400">Loading…</p>
          )}
          {q.isError && (
            <p className="px-4 py-6 text-sm text-rose-400">
              Could not load playlists
            </p>
          )}
          {!q.isLoading && !q.isError && hasPlaylists && (
            <ul className="divide-y divide-white/10">
              {playlists.map((p: PlaylistSummary) => {
                const busy = submittingPlaylistId === p.id;
                return (
                  <li key={p.id}>
                    <button
                      type="button"
                      disabled={listLocked}
                      className="flex w-full items-center justify-between px-4 py-3 text-left text-sm text-neutral-100 transition hover:bg-white/5 active:bg-white/10 disabled:cursor-wait disabled:opacity-60"
                      onClick={() => void handlePick(p.id, p.title)}
                    >
                      <span className="truncate font-medium">{p.title}</span>
                      <span className="ml-2 flex shrink-0 items-center gap-2 text-xs text-neutral-500">
                        {busy && (
                          <span
                            className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-neutral-500 border-t-transparent"
                            aria-hidden
                          />
                        )}
                        {p.is_public ? "Public" : "Private"}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
          {!q.isLoading && !q.isError && !hasPlaylists && !creatingInline && (
            <div className="px-4 py-8 text-center">
              <p className="text-sm text-neutral-400">
                You don&apos;t have any playlists yet.
              </p>
              <button
                type="button"
                disabled={listLocked}
                className="mt-4 rounded-lg bg-emerald-600/90 px-4 py-2 text-sm font-semibold text-white transition hover:bg-emerald-600 disabled:cursor-not-allowed disabled:opacity-50"
                onClick={() => setCreatingInline(true)}
              >
                Create playlist
              </button>
            </div>
          )}
          {!q.isLoading && !q.isError && hasPlaylists && !creatingInline && (
            <div className="border-t border-white/10">
              <button
                type="button"
                disabled={listLocked}
                className="flex w-full items-center px-4 py-3 text-left text-sm font-medium text-emerald-400/95 transition hover:bg-white/5 active:bg-white/10 disabled:cursor-not-allowed disabled:opacity-50"
                onClick={() => setCreatingInline(true)}
              >
                + Create new playlist
              </button>
            </div>
          )}
          {!q.isLoading && !q.isError && inlineCreateForm}
        </div>
        <div className="border-t border-white/10 px-4 py-3">
          <button
            type="button"
            disabled={listLocked}
            className="w-full rounded-lg border border-white/15 py-2 text-sm font-medium text-neutral-200 transition hover:bg-white/5 active:bg-white/10 disabled:opacity-50"
            onClick={closeModal}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
