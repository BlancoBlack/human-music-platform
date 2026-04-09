/**
 * Backend base URL (same origin-friendly for static /uploads).
 */
export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") ??
  "http://127.0.0.1:8000";

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

export async function fetchSong(songId: number): Promise<SongDetail> {
  const res = await fetch(`${API_BASE}/songs/${songId}`);
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
  const res = await fetch(`${API_BASE}/artists/${artistId}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Failed to load artist ${artistId}`);
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
