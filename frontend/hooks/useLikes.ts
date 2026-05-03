"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/context/ToastContext";
import {
  deleteLikeSong,
  fetchLikedSongIds,
  postLikeSong,
} from "@/lib/api";

/**
 * Server-backed likes with TanStack Query (`queryKey: ["likes"]`).
 * Optimistic updates with rollback on failure; `loadingSongIds` blocks double submits.
 */
export function useLikes(): {
  likedSongIds: Set<number>;
  loadingSongIds: Set<number>;
  like: (songId: number) => Promise<void>;
  unlike: (songId: number) => Promise<void>;
} {
  const { isAuthenticated, authReady } = useAuth();
  const { showError } = useToast();
  const queryClient = useQueryClient();
  const inFlight = useRef(new Set<number>());
  const [loadingSongIds, setLoadingSongIds] = useState<Set<number>>(
    () => new Set(),
  );

  const syncLoadingUi = useCallback(() => {
    setLoadingSongIds(new Set(inFlight.current));
  }, []);

  const query = useQuery({
    queryKey: ["likes"],
    queryFn: async () => {
      const ids = await fetchLikedSongIds();
      return new Set(ids);
    },
    enabled: Boolean(authReady && isAuthenticated),
  });

  useEffect(() => {
    if (authReady && !isAuthenticated) {
      queryClient.removeQueries({ queryKey: ["likes"] });
    }
  }, [authReady, isAuthenticated, queryClient]);

  const likedSongIds = useMemo(() => {
    if (!authReady || !isAuthenticated) return new Set<number>();
    return query.data ?? new Set<number>();
  }, [authReady, isAuthenticated, query.data]);

  const like = useCallback(
    async (songId: number) => {
      if (!isAuthenticated || inFlight.current.has(songId)) return;
      inFlight.current.add(songId);
      syncLoadingUi();
      const prev = queryClient.getQueryData<Set<number>>(["likes"]);
      const baseline = prev ? new Set(prev) : new Set<number>();
      queryClient.setQueryData<Set<number>>(["likes"], (old) => {
        const next = new Set(old ?? []);
        next.add(songId);
        return next;
      });
      try {
        await postLikeSong(songId);
      } catch (e) {
        console.error("[likes] like failed", e);
        queryClient.setQueryData(["likes"], baseline);
        showError("Could not update like");
      } finally {
        inFlight.current.delete(songId);
        syncLoadingUi();
      }
    },
    [isAuthenticated, queryClient, showError, syncLoadingUi],
  );

  const unlike = useCallback(
    async (songId: number) => {
      if (!isAuthenticated || inFlight.current.has(songId)) return;
      inFlight.current.add(songId);
      syncLoadingUi();
      const prev = queryClient.getQueryData<Set<number>>(["likes"]);
      const baseline = prev ? new Set(prev) : new Set<number>();
      queryClient.setQueryData<Set<number>>(["likes"], (old) => {
        const next = new Set(old ?? []);
        next.delete(songId);
        return next;
      });
      try {
        await deleteLikeSong(songId);
      } catch (e) {
        console.error("[likes] unlike failed", e);
        queryClient.setQueryData(["likes"], baseline);
        showError("Could not update like");
      } finally {
        inFlight.current.delete(songId);
        syncLoadingUi();
      }
    },
    [isAuthenticated, queryClient, showError, syncLoadingUi],
  );

  return { likedSongIds, loadingSongIds, like, unlike };
}
