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
  return fetch(url, {
    ...init,
    headers: merged,
    credentials: init.credentials ?? "include",
  });
}

export type SongDetail = {
  id: number;
  title: string;
  artist_id: number;
  upload_status: string;
  duration_seconds: number | null;
  featured_artist_ids: number[];
  credits: { name: string; role: string }[];
  has_master_audio: boolean;
  has_cover_art: boolean;
  cover_url: string | null;
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

export type ArtistPublic = {
  id: number;
  name: string;
};

export async function fetchArtist(artistId: number): Promise<ArtistPublic> {
  const res = await apiFetch(`/artists/${artistId}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Failed to load artist ${artistId}`);
  }
  return res.json();
}

export type ArtistsSearchResponse = {
  artists: ArtistPublic[];
};

export type ArtistCatalogSong = {
  id: number;
  title: string;
  artist_id: number;
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

export async function fetchDiscoveryHome(): Promise<DiscoveryResponse> {
  const res = await apiFetch("/discovery/home");
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "Failed to load discovery home");
  }
  return res.json();
}

export type UploadAudioErrorCode =
  | "wav_file_too_large"
  | "master_audio_immutable";

export type UploadCoverErrorCode = "cover_resolution_invalid";

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
