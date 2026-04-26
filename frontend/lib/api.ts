import { getAuthHeaders } from "@/lib/authHeaders";
import { API_BASE } from "@/lib/publicEnv";

export { API_BASE };

/** Authenticated API calls: merges `Authorization` when logged in; sends cookies for `/auth/*`. */
export async function apiFetch(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const url = `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
  const merged = new Headers(init.headers);
  const auth = getAuthHeaders();
  for (const [k, v] of Object.entries(auth)) {
    if (!merged.has(k)) merged.set(k, v);
  }
  const response = await fetch(url, {
    ...init,
    headers: merged,
    credentials: init.credentials ?? "include",
  });
  if (response.status === 401 || response.status === 403) {
    console.warn("[api] auth response", { path, status: response.status });
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
  upload_status: string;
  duration_seconds: number | null;
  featured_artist_ids: number[];
  credits: { name: string; role: string }[];
  splits?: { artist_id: number; share: number }[];
  has_master_audio: boolean;
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
  play_now: DiscoveryTrack[];
  for_you: DiscoveryTrack[];
  explore: DiscoveryTrack[];
  curated: DiscoveryTrack[];
  section_microcopy?: Record<string, string>;
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

export async function fetchArtistBySlug(slug: string): Promise<ArtistBySlugResponse> {
  const res = await apiFetch(`/artist/${encodeURIComponent(slug)}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Failed to load artist ${slug}`);
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
  user_id: number | null;
  artist_id: number;
  amount: number;
  status: string;
  created_at: string | null;
  attempt_count: number | null;
  failure_reason: string | null;
  algorand_tx_id: string | null;
  destination_wallet: string | null;
};

export async function fetchAdminPayouts(): Promise<AdminPayoutRow[]> {
  const res = await apiFetch("/admin/payouts");
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Failed to load admin payouts");
  }
  return res.json() as Promise<AdminPayoutRow[]>;
}

export async function fetchAdminPayoutsUi(): Promise<string> {
  const res = await apiFetch("/admin/payouts-ui");
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Failed to load admin payouts UI");
  }
  return res.text();
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
