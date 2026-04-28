/** Shared browser-safe API origin (avoid import cycles between `api` and `auth`). */
export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") ??
  "http://127.0.0.1:8000";
