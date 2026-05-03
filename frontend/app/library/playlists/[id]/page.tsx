"use client";

import {
  closestCenter,
  DndContext,
  DragOverlay,
  PointerSensor,
  type DragEndEvent,
  type DragMoveEvent,
  type DragStartEvent,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type CSSProperties,
  type ReactNode,
  type RefCallback,
} from "react";
import {
  type PlayableTrack,
  useAudioPlayer,
} from "@/components/audio/AudioPlayerProvider";
import { PlaylistCover } from "@/components/PlaylistCover";
import { SongActions } from "@/components/SongActions";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/context/ToastContext";
import {
  API_BASE,
  fetchPlaylistDetail,
  putPlaylistReorder,
  type PlaylistDetail,
  type PlaylistDetailTrack,
} from "@/lib/api";

function toPlayable(t: PlaylistDetailTrack): PlayableTrack {
  return {
    id: t.song_id,
    title: t.title,
    audioUrl: t.audio_url ? `${API_BASE}${t.audio_url}` : "",
    ...(t.cover_url != null ? { coverUrl: `${API_BASE}${t.cover_url}` } : {}),
  };
}

type TrackRowSharedProps = {
  row: PlaylistDetailTrack;
  rowIndex: number;
  playable: boolean;
  isCurrent: boolean;
  coverSrc: string | undefined;
  playFromIndex: (index: number) => void;
  isActivationClickSuppressed: () => boolean;
};

function GripIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="currentColor"
      className={className}
      aria-hidden
    >
      <circle cx="9" cy="8" r="1.35" />
      <circle cx="15" cy="8" r="1.35" />
      <circle cx="9" cy="12" r="1.35" />
      <circle cx="15" cy="12" r="1.35" />
      <circle cx="9" cy="16" r="1.35" />
      <circle cx="15" cy="16" r="1.35" />
    </svg>
  );
}

/** Visual-only clone for DragOverlay (no play, no SongActions). */
function PlaylistTrackDragOverlay({
  row,
  playable,
  isCurrent,
  coverSrc,
}: {
  row: PlaylistDetailTrack;
  playable: boolean;
  isCurrent: boolean;
  coverSrc: string | undefined;
}) {
  return (
    <div
      className={`pointer-events-none w-full max-w-3xl scale-[1.03] rounded-xl border opacity-95 shadow-lg dark:bg-neutral-950/50 ${
        isCurrent
          ? "border-emerald-500/45 bg-emerald-500/[0.09] dark:bg-emerald-500/12"
          : "border-neutral-200 bg-white dark:border-neutral-800"
      }`}
    >
      <div className="flex items-stretch gap-0 sm:gap-1">
        <div
          className="flex shrink-0 items-center px-2 py-3 text-neutral-400 dark:text-neutral-500"
          aria-hidden
        >
          <GripIcon className="h-5 w-5" />
        </div>
        <div className="flex min-w-0 flex-1 items-center gap-3 px-3 py-3 sm:gap-4 sm:px-4">
          <div className="relative flex h-12 w-10 shrink-0 items-center justify-center sm:h-14 sm:w-11">
            <span className="text-center text-sm tabular-nums text-neutral-500 dark:text-neutral-400">
              {row.position}
            </span>
          </div>
          <div className="relative h-12 w-12 shrink-0 overflow-hidden rounded-lg bg-neutral-200 dark:bg-neutral-800 sm:h-14 sm:w-14">
            {coverSrc ? (
              // eslint-disable-next-line @next/next/no-img-element -- API absolute URL
              <img
                src={coverSrc}
                alt=""
                className="h-full w-full object-cover"
              />
            ) : (
              <div className="flex h-full w-full items-center justify-center text-[10px] leading-tight text-neutral-500 dark:text-neutral-500">
                No cover
              </div>
            )}
          </div>
          {!playable ? (
            <span className="shrink-0 text-neutral-400 dark:text-neutral-500" aria-hidden>
              <svg
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={1.5}
                stroke="currentColor"
                className="h-5 w-5"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z"
                />
              </svg>
            </span>
          ) : null}
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium text-neutral-900 dark:text-neutral-100">
              {row.title}
            </p>
            <p className="truncate text-sm text-neutral-500 dark:text-neutral-400">
              {row.artist_name}
            </p>
          </div>
        </div>
        <div
          className="flex w-[5.25rem] shrink-0 items-center border-l border-neutral-100 px-2 dark:border-neutral-800/80 sm:w-[5.5rem]"
          aria-hidden
        />
      </div>
    </div>
  );
}

function PlaylistTrackRowInner({
  row,
  rowIndex,
  playable,
  isCurrent,
  coverSrc,
  playFromIndex,
  isActivationClickSuppressed,
  rowRef,
  rowStyle,
  dragHandle,
  showDropLineAbove,
}: TrackRowSharedProps & {
  rowRef?: RefCallback<HTMLLIElement>;
  rowStyle?: CSSProperties;
  dragHandle: ReactNode;
  showDropLineAbove?: boolean;
}) {
  return (
    <li
      ref={rowRef}
      style={rowStyle}
      data-playlist-track-active={isCurrent ? row.song_id : undefined}
      className={`group/row relative overflow-hidden rounded-xl border transition-colors duration-150 ease-out dark:bg-neutral-950/50 ${
        isCurrent
          ? "border-emerald-500/35 bg-emerald-500/[0.07] shadow-[inset_3px_0_0_0_rgb(16,185,129)] dark:bg-emerald-500/10"
          : "border-neutral-200 bg-white dark:border-neutral-800"
      }`}
    >
      {showDropLineAbove ? (
        <div
          className="pointer-events-none absolute left-2 right-2 top-0 z-10 h-0.5 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.45)]"
          aria-hidden
        />
      ) : null}
      <div className="flex items-stretch gap-0 sm:gap-1">
        {dragHandle}
        <div
          role={playable ? "button" : undefined}
          tabIndex={playable ? 0 : undefined}
          title={playable ? undefined : "Track not available"}
          className={`flex min-w-0 flex-1 items-center gap-3 px-3 py-3 sm:gap-4 sm:px-4 ${
            playable
              ? `group/play ${
                  isCurrent
                    ? "cursor-pointer rounded-xl transition-all duration-150 ease-out active:scale-[0.995]"
                    : "cursor-pointer rounded-xl transition-all duration-150 ease-out hover:bg-neutral-50/90 hover:shadow-sm active:scale-[0.995] dark:hover:bg-neutral-900/60"
                }`
              : "cursor-default opacity-45"
          }`}
          onClick={
            playable
              ? () => {
                  if (isActivationClickSuppressed()) return;
                  void playFromIndex(rowIndex);
                }
              : undefined
          }
          onKeyDown={
            playable
              ? (e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    void playFromIndex(rowIndex);
                  }
                }
              : undefined
          }
        >
          <div className="relative flex h-12 w-10 shrink-0 items-center justify-center sm:h-14 sm:w-11">
            <span
              className={`text-center text-sm tabular-nums text-neutral-500 transition-opacity duration-150 dark:text-neutral-400 ${
                playable ? "group-hover/play:pointer-events-none group-hover/play:opacity-0" : ""
              }`}
            >
              {row.position}
            </span>
            {playable ? (
              <span
                className="pointer-events-none absolute inset-0 flex items-center justify-center opacity-0 transition-opacity duration-150 group-hover/play:opacity-100 text-neutral-800 dark:text-neutral-100"
                aria-hidden
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 24 24"
                  fill="currentColor"
                  className="h-6 w-6 pl-0.5"
                >
                  <path d="M8 5v14l11-7L8 5z" />
                </svg>
              </span>
            ) : null}
          </div>
          <div className="relative h-12 w-12 shrink-0 overflow-hidden rounded-lg bg-neutral-200 dark:bg-neutral-800 sm:h-14 sm:w-14">
            {coverSrc ? (
              // eslint-disable-next-line @next/next/no-img-element -- API absolute URL
              <img
                src={coverSrc}
                alt=""
                className="h-full w-full object-cover"
              />
            ) : (
              <div className="flex h-full w-full items-center justify-center text-[10px] leading-tight text-neutral-500 dark:text-neutral-500">
                No cover
              </div>
            )}
          </div>
          {!playable ? (
            <span
              className="shrink-0 text-neutral-400 dark:text-neutral-500"
              aria-hidden
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={1.5}
                stroke="currentColor"
                className="h-5 w-5"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z"
                />
              </svg>
            </span>
          ) : null}
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium text-neutral-900 dark:text-neutral-100">
              {row.title}
            </p>
            <p className="truncate text-sm text-neutral-500 dark:text-neutral-400">
              {row.artist_name}
            </p>
          </div>
        </div>
        <div className="flex shrink-0 items-center border-l border-neutral-100 px-2 dark:border-neutral-800/80">
          <SongActions songId={row.song_id} />
        </div>
      </div>
    </li>
  );
}

function PlaylistTrackRowSortable(
  props: TrackRowSharedProps & { showDropLineAbove?: boolean },
) {
  const { showDropLineAbove, ...rowProps } = props;
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({
      id: props.row.song_id,
      transition: {
        duration: 150,
        easing: "ease-out",
      },
    });

  const rowStyle: CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition: transition
      ? `${transition}, opacity 150ms ease-out`
      : "opacity 150ms ease-out",
    ...(isDragging
      ? {
          opacity: 0,
          pointerEvents: "none" as const,
          zIndex: 0,
        }
      : {}),
  };

  const dragHandle = (
    <button
      type="button"
      className="touch-none shrink-0 cursor-grab border-0 bg-transparent px-1.5 py-3 text-neutral-400 opacity-0 transition-opacity duration-150 ease-out active:cursor-grabbing group-hover/row:opacity-100 hover:text-neutral-600 dark:text-neutral-500 dark:hover:text-neutral-300"
      aria-label="Drag to reorder"
      {...listeners}
      {...attributes}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
      }}
    >
      <GripIcon className="h-5 w-5 select-none" />
    </button>
  );

  return (
    <PlaylistTrackRowInner
      {...rowProps}
      rowRef={setNodeRef}
      rowStyle={rowStyle}
      dragHandle={dragHandle}
      showDropLineAbove={showDropLineAbove}
    />
  );
}

function PlaylistTrackRowStatic(props: TrackRowSharedProps) {
  return <PlaylistTrackRowInner {...props} dragHandle={null} />;
}

export default function LibraryPlaylistDetailPage() {
  const params = useParams();
  const raw = params.id;
  const idStr =
    typeof raw === "string" ? raw : Array.isArray(raw) ? (raw[0] ?? "") : "";
  const playlistId = Number.parseInt(idStr, 10);
  const idValid = Number.isFinite(playlistId) && playlistId >= 1;

  const { user, isAuthenticated, authReady } = useAuth();
  const queryClient = useQueryClient();
  const { showError } = useToast();
  const {
    playTrack,
    currentTrack,
    togglePlayback,
    isPlaying,
    isActivationClickSuppressed,
    replaceQueuePreservingPlayback,
    getPlaybackSource,
  } = useAudioPlayer();

  const [items, setItems] = useState<PlaylistDetailTrack[]>([]);
  const [dragActiveSongId, setDragActiveSongId] = useState<number | null>(null);
  const [dragOverSongId, setDragOverSongId] = useState<number | null>(null);

  const q = useQuery({
    queryKey: ["playlist", playlistId],
    queryFn: () => fetchPlaylistDetail(playlistId),
    enabled: authReady && isAuthenticated && idValid,
  });

  const sortedTracks = useMemo(() => {
    const rows = q.data?.tracks ?? [];
    return [...rows].sort((a, b) => a.position - b.position);
  }, [q.data?.tracks]);

  useEffect(() => {
    setItems([...sortedTracks]);
  }, [sortedTracks]);

  const ownerUserId = q.data?.owner_user_id;
  const isOwner =
    user?.id != null &&
    ownerUserId != null &&
    Number(user.id) === Number(ownerUserId);

  const displayTracks = useMemo(() => {
    if (!isOwner) return sortedTracks;
    if (sortedTracks.length === 0) return sortedTracks;
    if (items.length !== sortedTracks.length) return sortedTracks;
    return items;
  }, [isOwner, items, sortedTracks]);

  const reorderMutation = useMutation({
    mutationFn: (orderedSongIds: number[]) =>
      putPlaylistReorder(playlistId, orderedSongIds),
    onSuccess: async () => {
      await queryClient.refetchQueries({ queryKey: ["playlist", playlistId] });
      const detail = queryClient.getQueryData<PlaylistDetail>([
        "playlist",
        playlistId,
      ]);
      if (!detail?.tracks?.length) return;

      const src = getPlaybackSource();
      if (
        src?.source_type !== "playlist" ||
        src.source_id !== String(playlistId)
      ) {
        return;
      }

      const ordered = [...detail.tracks].sort((a, b) => a.position - b.position);
      replaceQueuePreservingPlayback(ordered.map(toPlayable));
    },
    onError: (err: Error) => {
      showError(err.message?.trim() ? err.message : "Could not reorder playlist");
      void queryClient.invalidateQueries({ queryKey: ["playlist", playlistId] });
    },
  });

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 6 },
    }),
  );

  const clearPlaylistDragUi = useCallback(() => {
    setDragActiveSongId(null);
    setDragOverSongId(null);
  }, []);

  const handlePlaylistDragStart = useCallback((event: DragStartEvent) => {
    const sid = Number(event.active.id);
    if (!Number.isFinite(sid)) return;
    setDragActiveSongId(sid);
    setDragOverSongId(sid);
  }, []);

  const handlePlaylistDragMove = useCallback((event: DragMoveEvent) => {
    if (event.over?.id == null) {
      setDragOverSongId(null);
      return;
    }
    const sid = Number(event.over.id);
    setDragOverSongId(Number.isFinite(sid) ? sid : null);
  }, []);

  const handlePlaylistDragEnd = useCallback(
    (event: DragEndEvent) => {
      clearPlaylistDragUi();
      const { active, over } = event;
      if (!over || active.id === over.id) return;
      setItems((current) => {
        const oldIndex = current.findIndex((t) => t.song_id === active.id);
        const newIndex = current.findIndex((t) => t.song_id === over.id);
        if (oldIndex < 0 || newIndex < 0) return current;
        const newOrder = arrayMove(current, oldIndex, newIndex);
        reorderMutation.mutate(newOrder.map((t) => t.song_id));
        return newOrder;
      });
    },
    [clearPlaylistDragUi, reorderMutation],
  );

  const queue = useMemo(() => displayTracks.map(toPlayable), [displayTracks]);

  const playbackSource = useMemo(() => {
    if (!q.data?.id) return null;
    return {
      source_type: "playlist" as const,
      source_id: String(q.data.id),
    };
  }, [q.data?.id]);

  const collageUrls = useMemo(() => {
    const urls = q.data?.cover_urls ?? [];
    return urls.filter((u): u is string => Boolean(u && String(u).trim()));
  }, [q.data?.cover_urls]);

  const firstPlayableIndex = useMemo(
    () => queue.findIndex((t) => Boolean(t.audioUrl)),
    [queue],
  );

  const playFromIndex = useCallback(
    async (index: number) => {
      if (!playbackSource || index < 0 || index >= queue.length) return;
      const track = queue[index];
      if (!track.audioUrl) return;
      await playTrack(track, {
        queue,
        queueIndex: index,
        playbackSource,
      });
    },
    [playbackSource, queue, playTrack],
  );

  const inThisQueue =
    currentTrack != null && queue.some((t) => t.id === currentTrack.id);

  const activeDragTrack = useMemo(() => {
    if (dragActiveSongId == null) return undefined;
    return displayTracks.find((t) => t.song_id === dragActiveSongId);
  }, [dragActiveSongId, displayTracks]);

  const handleHeaderPlay = useCallback(() => {
    if (firstPlayableIndex < 0 || !playbackSource) return;
    if (inThisQueue) {
      void togglePlayback();
      return;
    }
    void playFromIndex(firstPlayableIndex);
  }, [
    firstPlayableIndex,
    inThisQueue,
    playbackSource,
    playFromIndex,
    togglePlayback,
  ]);

  useEffect(() => {
    if (!currentTrack?.id || !inThisQueue) return;
    const el = document.querySelector(
      `[data-playlist-track-active="${currentTrack.id}"]`,
    );
    el?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [currentTrack?.id, inThisQueue]);

  if (!authReady) {
    return (
      <main className="mx-auto max-w-3xl px-4 py-10">
        <div className="h-8 w-56 animate-pulse rounded bg-neutral-200 dark:bg-neutral-800" />
        <div className="mt-8 h-40 animate-pulse rounded-xl bg-neutral-200 dark:bg-neutral-800" />
      </main>
    );
  }

  if (!isAuthenticated) {
    return (
      <main className="mx-auto max-w-3xl px-4 py-10">
        <h1 className="text-2xl font-semibold tracking-tight text-neutral-900 dark:text-neutral-100">
          Playlist
        </h1>
        <p className="mt-3 text-neutral-600 dark:text-neutral-400">
          Sign in to open this playlist.
        </p>
        <Link
          href={`/login?returnUrl=${encodeURIComponent(`/library/playlists/${idStr}`)}`}
          className="mt-4 inline-block text-sm font-medium text-emerald-600 hover:text-emerald-500 dark:text-emerald-400"
        >
          Log in
        </Link>
      </main>
    );
  }

  if (!idValid) {
    return (
      <main className="mx-auto max-w-3xl px-4 py-10">
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          Invalid playlist link.
        </p>
        <Link
          href="/library/playlists"
          className="mt-4 inline-block text-sm font-medium text-emerald-600 dark:text-emerald-400"
        >
          ← Back to playlists
        </Link>
      </main>
    );
  }

  if (q.isLoading) {
    return (
      <main className="mx-auto max-w-3xl px-4 py-10">
        <div className="h-8 w-48 animate-pulse rounded bg-neutral-200 dark:bg-neutral-800" />
        <div className="mt-6 flex gap-6">
          <div className="h-40 w-40 shrink-0 animate-pulse rounded-xl bg-neutral-200 dark:bg-neutral-800" />
          <div className="flex flex-1 flex-col gap-2 pt-2">
            <div className="h-6 w-3/4 animate-pulse rounded bg-neutral-200 dark:bg-neutral-800" />
            <div className="h-10 w-28 animate-pulse rounded-full bg-neutral-200 dark:bg-neutral-800" />
          </div>
        </div>
        <ul className="mt-10 space-y-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <li
              key={i}
              className="h-14 animate-pulse rounded-lg bg-neutral-200 dark:bg-neutral-800"
            />
          ))}
        </ul>
      </main>
    );
  }

  if (q.isError) {
    return (
      <main className="mx-auto max-w-3xl px-4 py-10">
        <p className="text-sm text-red-600 dark:text-red-400" role="alert">
          {q.error instanceof Error ? q.error.message : "Could not load playlist."}
        </p>
        <Link
          href="/library/playlists"
          className="mt-4 inline-block text-sm font-medium text-emerald-600 dark:text-emerald-400"
        >
          ← Back to playlists
        </Link>
      </main>
    );
  }

  const detail = q.data;
  if (!detail) return null;

  const showMetaRow = isOwner || detail.is_public;

  const canPlayAnything = firstPlayableIndex >= 0;

  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      <Link
        href="/library/playlists"
        className="text-sm font-medium text-neutral-600 transition-colors duration-150 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100"
      >
        ← Playlists
      </Link>

      <header className="mt-6 flex flex-col gap-6 sm:flex-row sm:items-start">
        <div className="mx-auto w-40 shrink-0 transition-transform duration-150 hover:scale-[1.02] sm:mx-0 sm:w-44">
          <PlaylistCover thumbnails={collageUrls} />
        </div>
        <div className="min-w-0 flex-1 text-center sm:text-left">
          <h1 className="text-2xl font-semibold tracking-tight text-neutral-900 dark:text-neutral-100">
            {detail.title}
          </h1>
          {showMetaRow ? (
            <p className="mt-1 flex flex-wrap items-center justify-center gap-2 text-sm text-neutral-500 dark:text-neutral-400 sm:justify-start">
              {isOwner ? <span>Your playlist</span> : null}
              {detail.is_public ? (
                <span className="rounded-full border border-neutral-300 px-2 py-0.5 text-xs dark:border-neutral-600">
                  Public
                </span>
              ) : null}
            </p>
          ) : null}
          <div className="mt-5 flex flex-wrap items-center justify-center gap-3 sm:justify-start">
            <button
              type="button"
              disabled={!canPlayAnything}
              title={
                !canPlayAnything
                  ? "No playable tracks (audio unavailable)"
                  : undefined
              }
              onClick={() => void handleHeaderPlay()}
              className="inline-flex items-center gap-2 rounded-full bg-emerald-600 px-5 py-2 text-sm font-semibold text-white shadow-sm transition-all duration-150 hover:bg-emerald-500 hover:shadow-md active:scale-95 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:scale-100"
            >
              {inThisQueue && isPlaying ? (
                <>
                  <span className="flex gap-0.5" aria-hidden>
                    <span className="block h-4 w-1 rounded-sm bg-white" />
                    <span className="block h-4 w-1 rounded-sm bg-white" />
                  </span>
                  Pause
                </>
              ) : (
                <>
                  <span className="text-lg leading-none" aria-hidden>
                    ▶
                  </span>
                  {inThisQueue ? "Resume" : "Play"}
                </>
              )}
            </button>
          </div>
        </div>
      </header>

      <section className="mt-10" aria-labelledby="playlist-tracks-heading">
        <h2
          id="playlist-tracks-heading"
          className="mb-3 text-sm font-semibold uppercase tracking-wide text-neutral-500 dark:text-neutral-400"
        >
          Tracks
        </h2>
        {sortedTracks.length === 0 ? (
          <p className="text-sm italic text-neutral-500 dark:text-neutral-400">
            No tracks in this playlist yet.
          </p>
        ) : isOwner ? (
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragStart={handlePlaylistDragStart}
            onDragMove={handlePlaylistDragMove}
            onDragEnd={handlePlaylistDragEnd}
            onDragCancel={clearPlaylistDragUi}
          >
            <SortableContext
              items={displayTracks.map((t) => t.song_id)}
              strategy={verticalListSortingStrategy}
            >
              <ul className="space-y-1 sm:space-y-1.5">
                {displayTracks.map((row, rowIndex) => {
                  const playable = Boolean(row.audio_url);
                  const isCurrent =
                    inThisQueue && currentTrack?.id === row.song_id;
                  const coverSrc = row.cover_url
                    ? `${API_BASE}${row.cover_url}`
                    : undefined;
                  const showDropLineAbove =
                    dragActiveSongId != null &&
                    dragOverSongId != null &&
                    dragActiveSongId !== dragOverSongId &&
                    row.song_id === dragOverSongId;
                  return (
                    <PlaylistTrackRowSortable
                      key={row.song_id}
                      row={row}
                      rowIndex={rowIndex}
                      playable={playable}
                      isCurrent={isCurrent}
                      coverSrc={coverSrc}
                      playFromIndex={playFromIndex}
                      isActivationClickSuppressed={isActivationClickSuppressed}
                      showDropLineAbove={showDropLineAbove}
                    />
                  );
                })}
              </ul>
            </SortableContext>
            <DragOverlay dropAnimation={{ duration: 180, easing: "ease-out" }}>
              {activeDragTrack ? (
                <PlaylistTrackDragOverlay
                  row={activeDragTrack}
                  playable={Boolean(activeDragTrack.audio_url)}
                  isCurrent={
                    inThisQueue &&
                    currentTrack?.id === activeDragTrack.song_id
                  }
                  coverSrc={
                    activeDragTrack.cover_url
                      ? `${API_BASE}${activeDragTrack.cover_url}`
                      : undefined
                  }
                />
              ) : null}
            </DragOverlay>
          </DndContext>
        ) : (
          <ul className="space-y-1 sm:space-y-1.5">
            {sortedTracks.map((row, rowIndex) => {
              const playable = Boolean(row.audio_url);
              const isCurrent =
                inThisQueue && currentTrack?.id === row.song_id;
              const coverSrc = row.cover_url
                ? `${API_BASE}${row.cover_url}`
                : undefined;
              return (
                <PlaylistTrackRowStatic
                  key={row.song_id}
                  row={row}
                  rowIndex={rowIndex}
                  playable={playable}
                  isCurrent={isCurrent}
                  coverSrc={coverSrc}
                  playFromIndex={playFromIndex}
                  isActivationClickSuppressed={isActivationClickSuppressed}
                />
              );
            })}
          </ul>
        )}
      </section>
    </main>
  );
}
