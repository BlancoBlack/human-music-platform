"use client";

import { API_BASE } from "@/lib/api";

type HubTab = "overview" | "analytics" | "payouts" | "upload";

type ArtistHubNavProps = {
  artistId: number;
  active: HubTab;
};

/**
 * Mirrors FastAPI artist HTML nav; Overview / Analytics / Payouts use API_BASE.
 */
export function ArtistHubNav({ artistId, active }: ArtistHubNavProps) {
  const id = artistId;
  const dash = `${API_BASE}/artist-dashboard/${id}`;
  const analytics = `${API_BASE}/artist-analytics/${id}`;
  const payouts = `${API_BASE}/artist-payouts/${id}`;
  const upload = `/artist-upload?artist_id=${id}`;

  const item = (tab: HubTab, href: string, label: string) => (
    <a
      href={href}
      className={
        active === tab
          ? "font-bold text-neutral-900 dark:text-neutral-100"
          : "text-neutral-600 underline-offset-4 hover:underline dark:text-neutral-400"
      }
    >
      {label}
    </a>
  );

  return (
    <nav
      className="mb-8 border-b border-neutral-200 pb-3 text-sm dark:border-neutral-800"
      aria-label="Artist hub"
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        {item("overview", dash, "Overview")}
        <span className="text-neutral-300 dark:text-neutral-600" aria-hidden>
          |
        </span>
        {item("analytics", analytics, "Analytics")}
        <span className="text-neutral-300 dark:text-neutral-600" aria-hidden>
          |
        </span>
        {item("payouts", payouts, "Payouts")}
        <span className="text-neutral-300 dark:text-neutral-600" aria-hidden>
          |
        </span>
        {item("upload", upload, "Upload")}
      </div>
    </nav>
  );
}
