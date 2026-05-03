import { getAuthHeaders, updateAccessToken } from "@/lib/authHeaders";
import { forceLogout } from "@/lib/authSessionManager";
import { API_BASE } from "@/lib/publicEnv";

export { API_BASE };

const ACCESS_TOKEN_STORAGE_KEY = "hm_access_token";
const JSON_HEADERS = { "Content-Type": "application/json" } as const;

let refreshPromise: Promise<string | null> | null = null;

function canUseStorage(): boolean {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

function setStoredAccessToken(token: string | null): void {
  if (!canUseStorage()) return;
  if (token && token.trim()) {
    window.localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, token.trim());
  } else {
    window.localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY);
  }
}

function applyAccessToken(token: string | null): void {
  updateAccessToken(token);
  setStoredAccessToken(token);
}

function shouldRefresh(path: string, responseStatus: number): boolean {
  if (responseStatus !== 401) return false;
  return path !== "/auth/refresh";
}

async function refreshAccessTokenSingleFlight(): Promise<string | null> {
  if (refreshPromise !== null) return refreshPromise;
  refreshPromise = (async (): Promise<string | null> => {
    const refreshRes = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({}),
      credentials: "include",
    });
    if (!refreshRes.ok) {
      await forceLogout("interceptor_refresh_failed_status");
      return null;
    }
    const tokens = (await refreshRes.json()) as {
      access_token?: string | null;
      refresh_token?: string | null;
    };
    const access = (tokens.access_token || "").trim();
    if (!access) {
      await forceLogout("interceptor_refresh_missing_access_token");
      return null;
    }
    applyAccessToken(access);
    return access;
  })()
    .catch(async (error) => {
      await forceLogout("interceptor_refresh_exception");
      throw error;
    })
    .finally(() => {
      refreshPromise = null;
    });
  return refreshPromise;
}

function buildHeaders(init: RequestInit): Headers {
  const merged = new Headers(init.headers);
  const auth = getAuthHeaders();
  for (const [k, v] of Object.entries(auth)) {
    if (!merged.has(k)) merged.set(k, v);
  }
  return merged;
}

/** Authenticated API calls: merges `Authorization` when logged in; sends cookies for `/auth/*`. */
export async function apiFetch(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const url = `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const hadAccessToken = Boolean(getAuthHeaders().Authorization);

  const perform = async (): Promise<Response> =>
    fetch(url, {
      ...init,
      headers: buildHeaders(init),
      credentials: init.credentials ?? "include",
    });

  let response = await perform();
  if (shouldRefresh(normalizedPath, response.status)) {
    try {
      const refreshedAccess = await refreshAccessTokenSingleFlight();
      if (refreshedAccess) {
        response = await perform();
      }
    } catch (error) {
      console.warn("[api] refresh failed", { path: normalizedPath, error });
    }
  }

  if (response.status === 401 || response.status === 403) {
    console.warn("[api] auth response", { path, status: response.status });
  }
  if (
    response.status === 401 &&
    hadAccessToken &&
    normalizedPath !== "/auth/refresh" &&
    normalizedPath !== "/auth/login" &&
    normalizedPath !== "/auth/register"
  ) {
    await forceLogout("unauthorized");
  }
  return response;
}

export type TaxonomyItem = {
  id: number;
  name: string;
  slug: string;
};

export type SongDetail = {
  id: number;
  slug: string;
  title: string;
  artist_id: number;
  release_id: number | null;
  upload_status: string;
  duration_seconds: number | null;
  featured_artist_ids: number[];
  credits: { name: string; role: string }[];
  splits?: { artist_id: number; share: number }[];
  has_master_audio: boolean;
  audio_url: string | null;
  has_cover_art: boolean;
  cover_url: string | null;
  genre_id?: number | null;
  subgenre_id?: number | null;
  genre?: TaxonomyItem | null;
  subgenre?: TaxonomyItem | null;
  moods?: string[] | null;
  country_code?: string | null;
  city?: string | null;
};

/** Thrown when `GET /songs/{id}` returns 404 (use for user-facing copy, not raw JSON). */
export class ApiNotFoundError extends Error {
  constructor(message = "Not found") {
    super(message);
    this.name = "ApiNotFoundError";
  }
}

/** HTTP 409 — e.g. payout batch lock held by another admin. */
export class ApiConflictError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ApiConflictError";
  }
}

export async function fetchSong(songId: number): Promise<SongDetail> {
  const res = await apiFetch(`/songs/${songId}`);
  if (res.status === 404) {
    throw new ApiNotFoundError("Song not found");
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Failed to load song ${songId}`);
  }
  return res.json();
}

export type PatchSongMetadataBody = {
  title: string;
  artist_id: number;
  featured_artist_ids: number[];
  credits: { name: string; role: string }[];
  genre_id?: number | null;
  subgenre_id?: number | null;
  moods?: string[];
  country_code?: string | null;
  city?: string | null;
};

export async function patchSongMetadata(
  songId: number,
  body: PatchSongMetadataBody,
): Promise<void> {
  const res = await apiFetch(`/songs/${songId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const { detail } = await parseErrorPayload(res);
    throw new Error(
      typeof detail === "string" && detail
        ? detail
        : `Failed to update song ${songId}`,
    );
  }
}

export async function deleteSong(songId: number): Promise<void> {
  const res = await apiFetch(`/songs/${songId}`, { method: "DELETE" });
  if (!res.ok) {
    const { detail } = await parseErrorPayload(res);
    throw new Error(
      typeof detail === "string" && detail
        ? detail
        : `Failed to delete song ${songId}`,
    );
  }
}

export type ArtistPublic = {
  id: number;
  name: string;
  slug: string;
};

export async function fetchArtist(artistId: number): Promise<ArtistPublic> {
  const res = await apiFetch(`/artists/${artistId}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Failed to load artist ${artistId}`);
  }
  return res.json();
}

export async function fetchGenres(): Promise<TaxonomyItem[]> {
  const res = await apiFetch("/genres");
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Failed to load genres");
  }
  return res.json();
}

export async function fetchSubgenresForGenre(
  genreId: number,
): Promise<TaxonomyItem[]> {
  const res = await apiFetch(`/genres/${genreId}/subgenres`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Failed to load subgenres for genre ${genreId}`);
  }
  return res.json();
}

export type ArtistsSearchResponse = {
  artists: ArtistPublic[];
};

export type GlobalSearchArtistResult = {
  type: "artist";
  id: number;
  name: string;
  slug: string;
};

export type GlobalSearchTrackResult = {
  type: "track";
  id: number;
  title: string;
  slug: string;
  artist: ArtistPublic;
  album: { id: number; title: string; slug: string } | null;
};

export type GlobalSearchAlbumResult = {
  type: "album";
  id: number;
  title: string;
  slug: string;
  artist: ArtistPublic;
};

export type GlobalSearchResult =
  | GlobalSearchArtistResult
  | GlobalSearchTrackResult
  | GlobalSearchAlbumResult;

export type GlobalSearchResponse = {
  results: GlobalSearchResult[];
  groups: {
    artists: GlobalSearchArtistResult[];
    tracks: GlobalSearchTrackResult[];
    albums: GlobalSearchAlbumResult[];
  };
  meta: {
    query: string;
    limit: number;
  };
};

export type ArtistCatalogSong = {
  id: number;
  slug: string;
  title: string;
  artist_id: number;
  release_id?: number | null;
  release_slug?: string | null;
  upload_status: string;
  duration_seconds: number | null;
  cover_url: string | null;
  audio_url: string | null;
  has_master_audio: boolean;
  playable: boolean;
};

export type ArtistCatalogResponse = {
  songs: ArtistCatalogSong[];
};

export async function fetchArtistSongs(
  artistId: number,
  limit = 50,
): Promise<ArtistCatalogResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  const res = await apiFetch(`/artists/${artistId}/songs?${params}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Failed to load songs for artist ${artistId}`);
  }
  return res.json();
}

export async function searchArtists(
  q: string,
  limit = 10,
): Promise<ArtistsSearchResponse> {
  const params = new URLSearchParams({ q, limit: String(limit) });
  const res = await apiFetch(`/artists/search?${params}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Artist search failed");
  }
  return res.json();
}

export async function searchGlobal(
  q: string,
  limit = 10,
): Promise<GlobalSearchResponse> {
  const params = new URLSearchParams({ q, limit: String(limit) });
  const res = await apiFetch(`/search?${params}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Global search failed");
  }
  return res.json();
}

export type DiscoveryTrack = {
  id: number;
  title: string;
  artist_name: string;
  audio_url: string | null;
  cover_url: string | null;
  playable: boolean;
  context_tag?: string | null;
};

export type DiscoveryResponse = {
  request_id: string;
  play_now: DiscoveryTrack[];
  for_you: DiscoveryTrack[];
  explore: DiscoveryTrack[];
  curated: DiscoveryTrack[];
  section_microcopy?: Record<string, string>;
};

export type DiscoveryPlayEventBody = {
  event_type: "play_click";
  request_id: string;
  song_id: number;
  section: "play_now" | "for_you" | "explore" | "curated";
  position: number;
  auth_state: "authenticated" | "anonymous";
  allowed_to_play: boolean;
  blocked_reason: "unauth" | "not_playable" | null;
  ranking_version?: string;
};

export type FirstSessionResponse = {
  tracks: DiscoveryTrack[];
  mode: "onboarding";
};

export async function fetchDiscoveryHome(): Promise<DiscoveryResponse> {
  const res = await apiFetch("/discovery/home");
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Failed to load discovery home");
  }
  return res.json();
}

/** GET /likes — requires auth */
export async function fetchLikedSongIds(): Promise<number[]> {
  const res = await apiFetch("/likes");
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Failed to load likes");
  }
  const j = (await res.json()) as { song_ids?: unknown };
  if (!Array.isArray(j.song_ids)) return [];
  return j.song_ids.map((id) => Number(id)).filter((n) => Number.isFinite(n));
}

export async function postLikeSong(songId: number): Promise<void> {
  const res = await apiFetch("/like", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ song_id: songId }),
  });
  if (!res.ok) {
    const { detail } = await parseErrorPayload(res);
    throw new Error(typeof detail === "string" && detail ? detail : "Like failed");
  }
}

export async function deleteLikeSong(songId: number): Promise<void> {
  const params = new URLSearchParams({ song_id: String(songId) });
  const res = await apiFetch(`/like?${params}`, { method: "DELETE" });
  if (!res.ok) {
    const { detail } = await parseErrorPayload(res);
    throw new Error(typeof detail === "string" && detail ? detail : "Unlike failed");
  }
}

export type PlaylistSummary = {
  id: number;
  title: string;
  is_public: boolean;
  /** Public media paths for collage (0–4); from first tracks by position, same hydration as playlist detail. */
  thumbnail_urls: string[];
};

export type PlaylistDetailTrack = {
  song_id: number;
  position: number;
  title: string;
  artist_name: string;
  cover_url: string | null;
  audio_url: string | null;
};

export type PlaylistDetail = {
  id: number;
  owner_user_id: number;
  title: string;
  description: string | null;
  is_public: boolean;
  created_at: string | null;
  updated_at: string | null;
  cover_urls: (string | null)[];
  tracks: PlaylistDetailTrack[];
};

/** GET /playlists/{id} — auth; enriched tracks + cover_urls (see backend). */
export async function fetchPlaylistDetail(playlistId: number): Promise<PlaylistDetail> {
  const res = await apiFetch(`/playlists/${playlistId}`);
  if (res.status === 404) {
    throw new Error("Playlist not found");
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Failed to load playlist");
  }
  return res.json() as Promise<PlaylistDetail>;
}

/** GET /playlists — auth; summaries only (no tracks) */
export async function fetchPlaylistSummaries(): Promise<PlaylistSummary[]> {
  const res = await apiFetch("/playlists");
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Failed to load playlists");
  }
  const j = (await res.json()) as { playlists?: PlaylistSummary[] };
  return Array.isArray(j.playlists) ? j.playlists : [];
}

/** POST /playlists — auth; body `{ title }` (optional fields omitted). */
export async function createPlaylist(title: string): Promise<{ id: number; title: string }> {
  const res = await apiFetch("/playlists", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: title.trim() }),
  });
  if (!res.ok) {
    const { detail } = await parseErrorPayload(res);
    throw new Error(
      typeof detail === "string" && detail ? detail : "Could not create playlist",
    );
  }
  const j = (await res.json()) as { id?: unknown; title?: unknown };
  const id = typeof j.id === "number" ? j.id : Number(j.id);
  const playlistTitle = typeof j.title === "string" ? j.title : "";
  if (!Number.isFinite(id) || id < 1 || !playlistTitle) {
    throw new Error("Invalid playlist response");
  }
  return { id, title: playlistTitle };
}

export async function addTrackToPlaylist(
  playlistId: number,
  songId: number,
): Promise<void> {
  const res = await apiFetch(`/playlists/${playlistId}/tracks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ song_id: songId }),
  });
  if (!res.ok) {
    const { detail } = await parseErrorPayload(res);
    throw new Error(
      typeof detail === "string" && detail ? detail : "Add to playlist failed",
    );
  }
}

/** PUT /playlists/{id}/reorder — auth; owner only; body `{ ordered_song_ids }` (full permutation). */
export async function putPlaylistReorder(
  playlistId: number,
  orderedSongIds: number[],
): Promise<void> {
  const res = await apiFetch(`/playlists/${playlistId}/reorder`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ordered_song_ids: orderedSongIds }),
  });
  if (!res.ok) {
    const { detail } = await parseErrorPayload(res);
    throw new Error(
      typeof detail === "string" && detail ? detail : "Could not reorder playlist",
    );
  }
}

export async function postDiscoveryEvent(body: DiscoveryPlayEventBody): Promise<void> {
  const res = await apiFetch("/discovery/events", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Failed to send discovery event");
  }
}

export async function submitOnboardingPreferences(payload: {
  genres: string[];
  artists: string[];
}): Promise<{ onboarding_completed: boolean; onboarding_step?: string | null }> {
  const res = await apiFetch("/onboarding/preferences", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Failed to save onboarding preferences");
  }
  return res.json();
}

export async function fetchFirstSession(): Promise<FirstSessionResponse> {
  const res = await apiFetch("/discovery/first-session", {
    method: "POST",
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Failed to load first playback session");
  }
  return res.json();
}

export type DiscoveryCtrRow = {
  impressions: number;
  clicks: number;
  ctr: number;
};

export type DiscoveryCtrBySectionRow = DiscoveryCtrRow & {
  section: string;
};

export type DiscoveryCtrByPositionRow = DiscoveryCtrRow & {
  global_position: number;
};

export type DiscoveryCandidatePoolRow = DiscoveryCtrRow & {
  candidate_pool: string;
};

export type DiscoveryCandidatePoolBySectionRow = DiscoveryCtrRow & {
  section: string;
  candidate_pool: string;
  share: number;
};

export type DiscoveryCtrByRankingVersionRow = DiscoveryCtrRow & {
  ranking_version: string;
};

export type DiscoveryTopArtistRow = {
  artist_id: number;
  artist_name?: string;
  impressions: number;
  share: number;
};

export type DiscoveryTopArtistsConcentration = {
  top_artists: DiscoveryTopArtistRow[];
  top_artists_share: number;
  total_impressions: number;
};

export type DiscoveryHighScoreLowCtrRow = {
  song_id: number;
  artist_id: number | null;
  song_title?: string;
  artist_name?: string;
  avg_score_play_now: number;
  impressions: number;
  clicks: number;
  ctr: number;
};

export type DiscoveryDiversityPerRequest = {
  avg_unique_artists: number;
  min_unique_artists: number;
  max_unique_artists: number;
};

export type DiscoveryScoreCtrCorrelationRow = DiscoveryCtrRow & {
  bucket: string;
};

export type AdminSignalHistogramBucket = {
  bucket: string;
  song_count: number;
};

export type AdminSignalReorderOverview = {
  row_count: number;
  distinct_users: number;
  distinct_songs: number;
};

export type AdminSignalReorderScale = {
  avg_weighted_sum: number;
  p95_weighted_sum: number;
};

export type AdminSignalTopReorderSong = {
  song_id: number;
  title: string;
  artist_name: string;
  weighted_sum: number;
  event_count: number;
};

export type AdminSignalReorderSnapshot = {
  window_days: number;
  overview: AdminSignalReorderOverview;
  scale: AdminSignalReorderScale;
  liked_share_of_weighted_sum: number;
  per_song_weighted_histogram: AdminSignalHistogramBucket[];
  top_reorder_songs: AdminSignalTopReorderSong[];
};

export type AdminSignalLikeOverview = {
  total_events: number;
  distinct_users: number;
  distinct_songs: number;
};

export type AdminSignalTopLikedSong = {
  song_id: number;
  title: string;
  artist_name: string;
  /** Display alias; same as `artist_name` when present */
  artist?: string;
  count: number;
};

export type AdminLikeRankingHistogramRow = {
  bucket: string;
  song_count: number;
};

export type AdminLikeRankingCorrelation = {
  avg_like_signal: number;
  avg_playlist_signal: number;
  pct_songs_with_like_and_playlist: number;
};

export type AdminLikeRankingAvgContributions = {
  playlist_boost: number;
  like_boost: number;
  reorder_boost: number | null;
  reorder_note: string;
};

export type AdminLikeRankingContext = {
  maturity_minutes: number;
  like_cap: number;
  like_cap_enabled: boolean;
  playlist_like_correlation_damp: number;
  sample_songs: number;
  like_signal_histogram: AdminLikeRankingHistogramRow[];
  like_boost_histogram: AdminLikeRankingHistogramRow[];
  correlation: AdminLikeRankingCorrelation;
  avg_contributions: AdminLikeRankingAvgContributions;
};

export type AdminSignalLikesSnapshot = {
  window_days: number;
  overview: AdminSignalLikeOverview;
  top_liked_songs: AdminSignalTopLikedSong[];
  ranking_context: AdminLikeRankingContext;
};

export type AdminSignalSnapshot = {
  reorder: AdminSignalReorderSnapshot;
  likes: AdminSignalLikesSnapshot;
  top_reorder_coverage_in_discovery: number;
  likes_reorder_overlap: number;
};

export type DiscoveryAdminAnalyticsResponse = {
  ctr_by_section: DiscoveryCtrBySectionRow[];
  ctr_by_position: DiscoveryCtrByPositionRow[];
  candidate_pool_performance: DiscoveryCandidatePoolRow[];
  candidate_pool_by_section: DiscoveryCandidatePoolBySectionRow[];
  ctr_by_ranking_version: DiscoveryCtrByRankingVersionRow[];
  top_artists_concentration: DiscoveryTopArtistsConcentration;
  high_score_low_ctr_anomalies: DiscoveryHighScoreLowCtrRow[];
  diversity_per_request: DiscoveryDiversityPerRequest;
  score_ctr_correlation: DiscoveryScoreCtrCorrelationRow[];
  signal_snapshot: AdminSignalSnapshot;
};

export async function fetchDiscoveryAdminAnalytics(): Promise<DiscoveryAdminAnalyticsResponse> {
  const res = await apiFetch("/discovery/admin/analytics");
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Failed to load discovery admin analytics");
  }
  return res.json();
}

export async function completeOnboarding(): Promise<{
  onboarding_completed: boolean;
  onboarding_step?: string | null;
}> {
  const res = await apiFetch("/onboarding/complete", { method: "POST" });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Failed to complete onboarding");
  }
  return res.json();
}

export type UploadAudioErrorCode =
  | "wav_file_too_large"
  | "master_audio_immutable";

export type UploadCoverErrorCode = "cover_resolution_invalid";

export type CreateReleaseDraftBody = {
  title: string;
  artist_id: number;
  release_type: "single" | "album";
  release_date: string;
};

export type CreateReleaseDraftResponse = {
  release_id: number;
  title: string;
  type: string;
};

export async function createReleaseDraft(
  body: CreateReleaseDraftBody,
): Promise<CreateReleaseDraftResponse> {
  const res = await apiFetch("/releases", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Failed to create release");
  }
  return res.json();
}

export type ReleaseTrackRow = {
  id: number;
  slug: string;
  title: string;
  track_number: number | null;
  state: string;
  upload_status: string;
  has_master_audio: boolean;
  has_cover_art: boolean;
  completion_status: string;
};

export type ReleaseTracksResponse = {
  tracks: ReleaseTrackRow[];
  progress: {
    total_tracks: number;
    completed_tracks: number;
    incomplete_tracks: number;
    empty_tracks: number;
  };
};

export async function fetchReleaseTracks(
  releaseId: number,
): Promise<ReleaseTracksResponse> {
  const res = await apiFetch(`/releases/${releaseId}/tracks`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Failed to load tracks for release ${releaseId}`);
  }
  return res.json();
}

export type ArtistBySlugResponse = {
  id: number;
  slug: string;
  name: string;
  canonical_url: string;
  songs: ArtistCatalogSong[];
};

export type ArtistReleasesBySlugResponse = {
  artist: {
    id: number;
    slug: string;
    name: string;
  };
  releases: StudioCatalogRelease[];
};

export type ArtistTracksBySlugResponse = {
  artist: {
    id: number;
    slug: string;
    name: string;
  };
  sort: StudioCatalogSort;
  tracks: StudioCatalogTrack[];
};

export async function fetchArtistBySlug(slug: string): Promise<ArtistBySlugResponse> {
  const res = await apiFetch(`/artist/${encodeURIComponent(slug)}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Failed to load artist ${slug}`);
  }
  return res.json();
}

export async function fetchArtistReleasesBySlug(
  slug: string,
): Promise<ArtistReleasesBySlugResponse> {
  const res = await apiFetch(`/artist/${encodeURIComponent(slug)}/releases`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Failed to load artist releases for ${slug}`);
  }
  return res.json();
}

export async function fetchArtistTracksBySlug(
  slug: string,
  sort: StudioCatalogSort = "top",
): Promise<ArtistTracksBySlugResponse> {
  const params = new URLSearchParams({ sort });
  const res = await apiFetch(`/artist/${encodeURIComponent(slug)}/tracks?${params}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Failed to load artist tracks for ${slug}`);
  }
  return res.json();
}

export type AlbumBySlugResponse = {
  id: number;
  slug: string;
  title: string;
  type: string;
  artist: ArtistPublic;
  release_date: string | null;
  state: string;
  canonical_url: string;
  tracks: ReleaseTrackRow[];
  progress: ReleaseTracksResponse["progress"];
};

export async function fetchAlbumBySlug(slug: string): Promise<AlbumBySlugResponse> {
  const res = await apiFetch(`/album/${encodeURIComponent(slug)}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Failed to load album ${slug}`);
  }
  return res.json();
}

export type TrackBySlugResponse = SongDetail & {
  artist: ArtistPublic;
  album: { id: number; slug: string; title: string } | null;
  canonical_url: string;
};

export async function fetchTrackBySlug(slug: string): Promise<TrackBySlugResponse> {
  const res = await apiFetch(`/track/${encodeURIComponent(slug)}`);
  if (!res.ok) {
    if (res.status === 404) {
      throw new ApiNotFoundError("Track not found");
    }
    const text = await res.text();
    throw new Error(text || `Failed to load track ${slug}`);
  }
  return res.json();
}

export type AdminPayoutRow = {
  id: string;
  batch_id: number;
  batch_status?: string;
  distinct_users?: number | null;
  user_id: number | null;
  artist_id: number;
  artist_name?: string | null;
  amount: number;
  ui_status?: string;
  status: string;
  created?: string | null;
  created_at: string | null;
  attempts?: number | null;
  attempt_count: number | null;
  failure_reason: string | null;
  tx?: { tx_id: string | null; explorer_url: string | null } | null;
  wallet?: string | null;
  algorand_tx_id: string | null;
  tx_id?: string | null;
  destination_wallet: string | null;
};

export type AdminPayoutFilters = {
  status?: string;
  artist_id?: number;
  artist_name?: string;
  limit?: number;
};

export async function fetchAdminPayouts(
  filters: AdminPayoutFilters = {},
): Promise<AdminPayoutRow[]> {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (typeof filters.artist_id === "number") {
    params.set("artist_id", String(filters.artist_id));
  }
  if (filters.artist_name) params.set("artist_name", filters.artist_name);
  if (typeof filters.limit === "number") params.set("limit", String(filters.limit));
  const query = params.toString();
  const res = await apiFetch(query ? `/admin/payouts?${query}` : "/admin/payouts");
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Failed to load admin payouts");
  }
  return res.json() as Promise<AdminPayoutRow[]>;
}

const BATCH_LOCK_CONFLICT =
  "Batch is currently being processed by another admin";

export async function postAdminSettleBatch(batchId: number): Promise<void> {
  const res = await apiFetch(`/admin/settle-batch/${batchId}`, {
    method: "POST",
  });
  if (res.status === 409) {
    const { detail } = await parseErrorPayload(res);
    throw new ApiConflictError(
      typeof detail === "string" && detail.trim()
        ? detail.trim()
        : BATCH_LOCK_CONFLICT,
    );
  }
  if (!res.ok) {
    const { detail } = await parseErrorPayload(res);
    throw new Error(
      typeof detail === "string" && detail
        ? detail
        : `Failed to settle batch ${batchId}`,
    );
  }
}

export type AdminRetryBatchResult = {
  retried: number;
  success: number;
  failed: number;
};

export async function postAdminRetryBatch(
  batchId: number,
): Promise<AdminRetryBatchResult> {
  const res = await apiFetch(`/admin/retry-batch/${batchId}`, {
    method: "POST",
  });
  if (res.status === 409) {
    const { detail } = await parseErrorPayload(res);
    throw new ApiConflictError(
      typeof detail === "string" && detail.trim()
        ? detail.trim()
        : BATCH_LOCK_CONFLICT,
    );
  }
  if (!res.ok) {
    const { detail } = await parseErrorPayload(res);
    throw new Error(
      typeof detail === "string" && detail
        ? detail
        : `Failed to retry batch ${batchId}`,
    );
  }
  return res.json() as Promise<AdminRetryBatchResult>;
}

export type AdminActionLogRow = {
  admin_user_id: number;
  admin_user_email: string | null;
  action_type: string;
  target_id: number;
  created_at: string | null;
  metadata?: Record<string, unknown> | null;
};

export async function fetchAdminActionLogs(limit = 50): Promise<AdminActionLogRow[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  const res = await apiFetch(`/admin/action-logs?${params}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Failed to load admin action logs");
  }
  return res.json() as Promise<AdminActionLogRow[]>;
}

export async function uploadReleaseCover(
  releaseId: number,
  file: File,
): Promise<void> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await apiFetch(`/releases/${releaseId}/upload-cover`, {
    method: "POST",
    body: fd,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Failed to upload release cover");
  }
}

export type CreateSongWithReleaseBody = {
  title: string;
  artist_id: number;
  release_id: number;
  featured_artist_ids: number[];
  credits: { name: string; role: string }[];
  genre_id?: number | null;
  subgenre_id?: number | null;
  moods?: string[];
  country_code?: string | null;
  city?: string | null;
};

export type SongSplitRow = {
  artist_id: number;
  share: number;
};

export async function putSongSplits(
  songId: number,
  splits: SongSplitRow[],
): Promise<void> {
  const res = await apiFetch(`/songs/${songId}/splits`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ splits }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Failed to save royalty splits");
  }
}

export async function createSongWithRelease(
  body: CreateSongWithReleaseBody,
): Promise<{ song_id: number }> {
  const res = await apiFetch("/songs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Failed to create song");
  }
  return res.json();
}

export async function parseErrorPayload(res: Response): Promise<{
  code?: string;
  detail?: string;
}> {
  const text = await res.text();
  try {
    const j = JSON.parse(text) as { error?: string; detail?: unknown };
    if (typeof j.error === "string") return { code: j.error };
    if (j.detail !== undefined) {
      const d = j.detail;
      const detail =
        typeof d === "string"
          ? d
          : Array.isArray(d)
            ? (d as { msg?: string }[])
                .map((x) => x.msg)
                .filter(Boolean)
                .join("; ")
            : String(d);
      return { detail };
    }
  } catch {
    /* ignore */
  }
  return { detail: text || res.statusText };
}

export type StudioArtistRef = {
  id: number;
  name: string;
};

export type StudioReleaseSummary = {
  id: number;
  title: string;
  cover_url: string | null;
  artist: StudioArtistRef;
  type: "single" | "ep" | "album";
  created_at: string | null;
  track_count: number;
  split_version: number;
};

export type StudioPendingSummary = {
  split: number;
  feature: number;
};

export type StudioPendingListParticipant = {
  artist_id: number;
  artist_name: string;
  role: "primary" | "collaborator" | "featured";
  status: "pending" | "accepted" | "rejected";
  approval_type: "split" | "feature" | "none";
  blocking: boolean;
  is_actionable_for_user: boolean;
};

export type StudioPendingListItem = {
  release: StudioReleaseSummary;
  approval_status: "draft" | "pending_approvals" | "ready";
  pending_summary: StudioPendingSummary;
  participants: StudioPendingListParticipant[];
};

export type StudioSongFeaturedArtist = {
  artist_id: number;
  artist_name: string;
};

export type StudioSongCredit = {
  name: string;
  role: string;
};

export type StudioSong = {
  id: number;
  title: string;
  primary_artist_id: number;
  featured_artists: StudioSongFeaturedArtist[];
  credits: StudioSongCredit[];
};

export type StudioSplit = {
  artist_id: number;
  artist_name: string;
  share: number;
};

export type StudioParticipant = {
  artist_id: number;
  artist_name: string;
  role: "primary" | "collaborator" | "featured";
  status: "pending" | "accepted" | "rejected";
  approval_type: "split" | "feature" | "none";
  requires_approval: boolean;
  blocking: boolean;
  is_actionable_for_user: boolean;
  has_feature_context: boolean;
  rejection_reason: string | null;
  approved_at: string | null;
};

export type StudioReleaseDetail = {
  release: StudioReleaseSummary & {
    approval_status: "draft" | "pending_approvals" | "ready";
    genres: string[];
    moods: string[];
    location: string | null;
  };
  user_context: {
    owned_artist_ids: number[];
    pending_actions_count: number;
  };
  songs: StudioSong[];
  splits: StudioSplit[];
  participants: StudioParticipant[];
  pending_summary: StudioPendingSummary;
};

export type StudioApprovalActionBody = {
  artist_id: number;
  reason?: string;
};

export type StudioApprovalActionResponse = {
  status: "accepted" | "rejected";
  updated_participant: {
    artist_id: number;
    role: "primary" | "collaborator" | "featured";
    approval_type: "split" | "feature" | "none";
    blocking: boolean;
    status: "pending" | "accepted" | "rejected";
    rejection_reason: string | null;
    approved_at: string | null;
  };
  release_approval_status: "draft" | "pending_approvals" | "ready" | null;
};

export type StudioContextRef = { type: "user" | "artist" | "label"; id: number };

export type StudioMeResponse = {
  user: { id: number; email: string | null };
  allowed_contexts: {
    artists: { id: number; name: string; slug: string }[];
    labels: { id: number; name: string }[];
  };
  current_context: StudioContextRef;
};

export async function fetchStudioMe(): Promise<StudioMeResponse> {
  const res = await apiFetch("/studio/me");
  if (!res.ok) {
    const { detail } = await parseErrorPayload(res);
    throw new Error(detail || "Failed to load studio context");
  }
  return res.json();
}

export type StudioArtistAnalyticsTopSong = {
  song_id: number;
  title: string;
  streams: number;
};

export type StudioArtistAnalyticsTopFanSong = {
  song_id: number;
  title: string;
  streams: number;
};

export type StudioArtistAnalyticsTopFan = {
  user_id: number;
  username: string;
  streams: number;
  top_song: StudioArtistAnalyticsTopFanSong;
};

export type StudioArtistAnalyticsResponse = {
  range: string;
  streams: Record<string, number>;
  top_songs: StudioArtistAnalyticsTopSong[];
  top_fans: StudioArtistAnalyticsTopFan[];
};

export async function fetchStudioArtistAnalytics(
  artistId: number,
  range: string,
): Promise<StudioArtistAnalyticsResponse> {
  const params = new URLSearchParams({ range });
  const res = await apiFetch(`/studio/${artistId}/analytics?${params}`);
  if (!res.ok) {
    const { detail } = await parseErrorPayload(res);
    throw new Error(
      typeof detail === "string" && detail.trim()
        ? detail
        : `Failed to load analytics for artist ${artistId}`,
    );
  }
  return res.json() as Promise<StudioArtistAnalyticsResponse>;
}

export type ArtistDashboardLastPayout = {
  batch_id: number;
  payout_date: string | null;
  amount: number;
};

export type ArtistDashboardEarningsPerSong = {
  song_id: number;
  total: number;
  paid: number;
  pending: number;
};

export type ArtistDashboardPayoutRow = {
  song_id: number;
  amount: number;
  status: string;
};

export type ArtistDashboardResponse = {
  artist_id: number;
  total: number;
  paid: number;
  accrued: number;
  failed_settlement: number;
  pending: number;
  spotify_total: number;
  difference: number;
  earnings_per_song: ArtistDashboardEarningsPerSong[];
  top_songs: ArtistDashboardEarningsPerSong[];
  last_payouts: ArtistDashboardLastPayout[];
  payouts: ArtistDashboardPayoutRow[];
};

export type StudioPayoutSummary = {
  paid_eur: number;
  accrued_eur: number;
  pending_eur: number;
  failed_eur: number;
  batch_count: number;
  last_batch_date: string | null;
};

export type StudioPayoutHistoryRow = {
  batch_id: string;
  date: string;
  amount_eur: number;
  status: "paid" | "pending" | "failed";
  users: number;
  tx_id?: string | null;
  explorer_url?: string | null;
};

export type StudioPayoutMethod = {
  selected: "crypto" | "bank" | "none";
  supports_onchain_settlement: boolean;
  requires_manual_settlement: boolean;
  wallet_address: string | null;
  bank_configured: boolean;
};

export type StudioArtistPayoutsResponse = {
  summary: StudioPayoutSummary;
  history: StudioPayoutHistoryRow[];
  payout_method: StudioPayoutMethod;
};

export type StudioPayoutMethodUpdateResponse = {
  success: boolean;
  payout_method: {
    selected: "crypto" | "bank" | "none";
    wallet_address: string | null;
    bank_configured: boolean;
  };
};

export async function fetchStudioArtistDashboard(
  artistId: number,
): Promise<ArtistDashboardResponse> {
  const res = await apiFetch(`/studio/${artistId}/dashboard`);
  if (!res.ok) {
    const { detail } = await parseErrorPayload(res);
    throw new Error(detail || `Failed to load dashboard for artist ${artistId}`);
  }
  return res.json();
}

export async function fetchStudioArtistPayouts(
  artistId: number,
): Promise<StudioArtistPayoutsResponse> {
  const res = await apiFetch(`/studio/${artistId}/payouts`);
  if (!res.ok) {
    const { detail } = await parseErrorPayload(res);
    throw new Error(detail || `Failed to load payouts for artist ${artistId}`);
  }
  return res.json();
}

export async function postStudioArtistPayoutMethod(
  artistId: number,
  payload: {
    payout_method: "crypto" | "bank" | "none";
    payout_wallet_address?: string;
    payout_bank_info?: string;
  },
): Promise<StudioPayoutMethodUpdateResponse> {
  const body = new FormData();
  body.append("payout_method", payload.payout_method);
  body.append("payout_wallet_address", payload.payout_wallet_address ?? "");
  body.append("payout_bank_info", payload.payout_bank_info ?? "");
  const res = await apiFetch(`/artist/${artistId}/payout-method`, {
    method: "POST",
    body,
  });
  if (!res.ok) {
    const { detail } = await parseErrorPayload(res);
    throw new Error(detail || "Failed to update payout method");
  }
  return res.json();
}

export type ArtistInsightStoryType =
  | "no_songs"
  | "no_streams"
  | "early_listeners"
  | "first_fans"
  | "first_replays"
  | "fan_engagement"
  | "top_fan_week"
  | "fans_reached"
  | (string & {});

export type ArtistInsightStory = {
  type: ArtistInsightStoryType;
  priority: number;
  message: string;
  data: Record<string, unknown>;
};

export type ArtistInsightsResponse = {
  range: string;
  stories: ArtistInsightStory[];
};

export async function fetchArtistInsights(
  artistId: number,
  range: string = "last_30_days",
): Promise<ArtistInsightsResponse> {
  const params = new URLSearchParams({ range });
  const res = await apiFetch(`/artist/${artistId}/insights?${params}`);
  if (!res.ok) {
    const { detail } = await parseErrorPayload(res);
    throw new Error(detail || `Failed to load insights for artist ${artistId}`);
  }
  return res.json();
}

export type StudioCatalogSort = "top" | "new" | "old";

export type StudioCatalogTrack = {
  id: number;
  slug: string;
  title: string;
  artist_name: string;
  duration_seconds: number | null;
  release_date: string | null;
  stream_count: number;
  cover_url: string | null;
  audio_url: string | null;
  playable: boolean;
};

export type StudioCatalogRelease = {
  id: number;
  slug: string;
  title: string;
  type: string;
  release_date: string | null;
  cover_url: string | null;
  /** First ready track on the release (album order); null if none. */
  first_track?: StudioCatalogTrack | null;
};

export type StudioCatalogResponse = {
  artist_id: number;
  sort: StudioCatalogSort;
  releases: StudioCatalogRelease[];
  tracks: StudioCatalogTrack[];
};

export type StudioReleasesResponse = {
  releases: StudioCatalogRelease[];
};

export async function fetchStudioCatalog(
  artistId: number,
  sort: StudioCatalogSort = "top",
): Promise<StudioCatalogResponse> {
  const params = new URLSearchParams({ sort });
  const res = await apiFetch(`/studio/${artistId}/catalog?${params}`);
  if (!res.ok) {
    const { detail } = await parseErrorPayload(res);
    throw new Error(detail || `Failed to load catalog for artist ${artistId}`);
  }
  return res.json();
}

export async function fetchStudioReleases(artistId: number): Promise<StudioReleasesResponse> {
  const res = await apiFetch(`/studio/${artistId}/releases`);
  if (!res.ok) {
    const { detail } = await parseErrorPayload(res);
    throw new Error(detail || `Failed to load releases for artist ${artistId}`);
  }
  return res.json();
}

export async function fetchStudioPendingApprovalsList(): Promise<StudioPendingListItem[]> {
  const res = await apiFetch("/studio/pending-approvals?view=list");
  if (!res.ok) {
    const { detail } = await parseErrorPayload(res);
    throw new Error(detail || "Failed to load pending approvals");
  }
  return res.json();
}

export type StudioReleasePublishResponse = {
  release_id: number;
  state: "published" | "scheduled" | string;
  discoverable_at: string | null;
};

export async function postStudioReleasePublish(
  releaseId: number,
): Promise<StudioReleasePublishResponse> {
  const res = await apiFetch(`/studio/releases/${releaseId}/publish`, {
    method: "POST",
  });
  if (!res.ok) {
    const { detail } = await parseErrorPayload(res);
    throw new Error(detail || "Publish request failed");
  }
  return res.json();
}

export async function fetchStudioReleaseDetail(
  releaseId: number,
): Promise<StudioReleaseDetail> {
  const res = await apiFetch(`/studio/releases/${releaseId}`);
  if (!res.ok) {
    const { detail } = await parseErrorPayload(res);
    throw new Error(detail || `Failed to load release ${releaseId}`);
  }
  return res.json();
}

export async function postStudioReleaseApprove(
  releaseId: number,
  body: StudioApprovalActionBody,
): Promise<StudioApprovalActionResponse> {
  const res = await apiFetch(`/studio/releases/${releaseId}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const { detail } = await parseErrorPayload(res);
    throw new Error(detail || "Approval request failed");
  }
  return res.json();
}

export async function postStudioReleaseReject(
  releaseId: number,
  body: StudioApprovalActionBody,
): Promise<StudioApprovalActionResponse> {
  const res = await apiFetch(`/studio/releases/${releaseId}/reject`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const { detail } = await parseErrorPayload(res);
    throw new Error(detail || "Rejection request failed");
  }
  return res.json();
}
