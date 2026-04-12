import { API_BASE } from "@/lib/publicEnv";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** MVP: must match a real user row; override via NEXT_PUBLIC_LISTENING_USER_ID */
export function getListeningUserId(): string {
  const raw = process.env.NEXT_PUBLIC_LISTENING_USER_ID?.trim();
  return raw && raw.length > 0 ? raw : "1";
}

export function listeningHeaders(): HeadersInit {
  return {
    "Content-Type": "application/json",
    "X-User-Id": getListeningUserId(),
  };
}

export type StartSessionResponse = { session_id: number };

/** Always send `{ song_id: number }`; unwrap accidental `{ song_id: { song_id: n } }` at runtime. */
function coerceStartSessionSongId(songId: number): number {
  let raw: unknown = songId as unknown;
  if (typeof raw === "object" && raw !== null && "song_id" in raw) {
    raw = (raw as { song_id: unknown }).song_id;
  }
  const n = Math.trunc(Number(raw));
  if (!Number.isFinite(n) || n < 1) {
    throw new Error(
      `postStartSession: song_id must be a positive integer (got ${JSON.stringify(songId)})`,
    );
  }
  return n;
}

export async function postStartSession(songId: number): Promise<StartSessionResponse> {
  const song_id = coerceStartSessionSongId(songId);
  const res = await fetch(`${API_BASE}/stream/start-session`, {
    method: "POST",
    headers: listeningHeaders(),
    body: JSON.stringify({ song_id }),
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(t || `start-session failed (${res.status})`);
  }
  return res.json();
}

export type CheckpointResponse = {
  status: string;
  checkpoint_id: number;
  session_id: number;
};

export async function postCheckpoint(body: {
  session_id: number;
  song_id: number;
  sequence: number;
  position_seconds: number;
}): Promise<Response> {
  return fetch(`${API_BASE}/stream/checkpoint`, {
    method: "POST",
    headers: listeningHeaders(),
    body: JSON.stringify(body),
  });
}

export type FinalizeResponse = {
  status: string;
  event_id: number | null;
  listening_session_id: number | null;
  is_valid: boolean;
  validation_reason: string | null;
};

export async function postFinalize(
  body: {
    song_id: number;
    duration: number;
    session_id: number;
    idempotency_key: string;
  },
  opts?: { keepalive?: boolean },
): Promise<Response> {
  return fetch(`${API_BASE}/stream`, {
    method: "POST",
    headers: listeningHeaders(),
    body: JSON.stringify(body),
    keepalive: opts?.keepalive === true,
  });
}

/** Retries finalize with the same idempotency_key (safe for duplicates). */
export async function postFinalizeWithRetry(
  body: {
    song_id: number;
    duration: number;
    session_id: number;
    idempotency_key: string;
  },
  opts?: { attempts?: number; keepalive?: boolean },
): Promise<FinalizeResponse> {
  const attempts = opts?.attempts ?? 3;
  const keepalive = opts?.keepalive === true;
  let lastText = "";
  for (let i = 0; i < attempts; i++) {
    const res = await postFinalize(body, { keepalive });
    lastText = await res.text();
    if (res.ok) {
      try {
        return JSON.parse(lastText) as FinalizeResponse;
      } catch {
        throw new Error("Invalid finalize JSON");
      }
    }
    if (res.status >= 400 && res.status < 500 && res.status !== 429) {
      throw new Error(lastText || `Finalize failed (${res.status})`);
    }
    await sleep(400 * (i + 1));
  }
  throw new Error(lastText || "Finalize failed after retries");
}
