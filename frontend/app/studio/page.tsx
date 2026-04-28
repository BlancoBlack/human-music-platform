"use client";

import { useEffect, useMemo, useState } from "react";
import {
  fetchArtistInsights,
  fetchStudioArtistDashboard,
  fetchStudioMe,
  type ArtistDashboardResponse,
  type ArtistInsightStory,
} from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

function capitalize(value: string): string {
  if (!value) return value;
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function resolveStudioName(input: {
  displayName: string | null | undefined;
  email: string | null | undefined;
  id: number | null | undefined;
}): string {
  const byDisplay = String(input.displayName || "").trim();
  if (byDisplay) return capitalize(byDisplay);
  const byEmail = String(input.email || "").trim();
  if (byEmail) return capitalize(byEmail.split("@")[0] || byEmail);
  if (typeof input.id === "number" && Number.isFinite(input.id)) {
    return `Artist ${input.id}`;
  }
  return "Studio";
}

/** Mirrors Python f-string default repr for `round(x, 2)` (e.g. 5 → "5.0", 5.5 → "5.5", 5.55 → "5.55"). */
function formatEuroAmount(value: number | null | undefined): string {
  const v = Number(value ?? 0);
  const rounded = Math.round(v * 100) / 100;
  if (Number.isInteger(rounded)) return `${rounded}.0`;
  return String(rounded);
}

/** First day of next calendar month, ISO `YYYY-MM-DD`. Matches legacy `date.today()` behavior. */
function nextPayoutIsoDate(today: Date = new Date()): string {
  const next = new Date(today.getFullYear(), today.getMonth() + 1, 1);
  const yyyy = next.getFullYear();
  const mm = String(next.getMonth() + 1).padStart(2, "0");
  return `${yyyy}-${mm}-01`;
}

/** Port of legacy `heroInsightSubtext` (artist-dashboard HTML). */
function deriveInsightSubtext(story: ArtistInsightStory): string {
  if (!story || typeof story !== "object") return "";
  const d = (story.data ?? {}) as Record<string, unknown>;
  const t = String(story.type || "");
  if (t === "fan_engagement") {
    const u = d.username != null ? String(d.username) : "";
    const song = d.song_title != null ? String(d.song_title) : "";
    if (u || song) {
      return `Fan: ${u || "—"} — Song: ${song || "—"}`;
    }
    return "";
  }
  if (t === "early_listeners" && d.listeners != null && d.listeners !== "") {
    return `${String(d.listeners)} listeners discovered your music`;
  }
  if (t === "top_fan_week") {
    const u2 = d.username != null ? String(d.username) : "";
    if (u2 && d.streams != null && d.streams !== "") {
      return `Fan: ${u2} — ${String(d.streams)} listens in the last 7 days`;
    }
    if (u2) return `Fan: ${u2}`;
    return "";
  }
  if (t === "fans_reached" && d.listeners != null && d.listeners !== "") {
    return `${String(d.listeners)} unique listeners in the last 30 days`;
  }
  return "";
}

type DashboardState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "no_artist" }
  | { status: "ready"; artistId: number; dashboard: ArtistDashboardResponse; story: ArtistInsightStory | null }
  | { status: "error"; message: string };

export default function StudioDashboardPage() {
  const { user, authReady, isAuthenticated } = useAuth();
  const studioName = useMemo(
    () =>
      resolveStudioName({
        displayName: user?.display_name,
        email: user?.email,
        id: user?.id,
      }),
    [user?.display_name, user?.email, user?.id],
  );

  const [state, setState] = useState<DashboardState>({ status: "idle" });
  const [showComparisonDetails, setShowComparisonDetails] = useState(false);
  const nextPayoutDate = useMemo(() => nextPayoutIsoDate(), []);

  useEffect(() => {
    if (!authReady) return;
    if (!isAuthenticated) {
      setState({ status: "idle" });
      return;
    }

    let cancelled = false;
    setState({ status: "loading" });
    setShowComparisonDetails(false);

    void (async () => {
      try {
        const me = await fetchStudioMe();
        let artistId: number | null = null;
        if (me.current_context?.type === "artist") {
          artistId = Number(me.current_context.id);
        }
        if (artistId == null && Array.isArray(me.allowed_contexts?.artists)) {
          const first = me.allowed_contexts.artists[0];
          if (first && Number.isFinite(first.id)) artistId = Number(first.id);
        }
        if (artistId == null) {
          if (!cancelled) setState({ status: "no_artist" });
          return;
        }

        const [dashboard, insights] = await Promise.all([
          fetchStudioArtistDashboard(artistId),
          fetchArtistInsights(artistId, "last_30_days").catch(() => ({
            range: "last_30_days",
            stories: [],
          })),
        ]);

        const story =
          Array.isArray(insights.stories) && insights.stories.length > 0
            ? insights.stories[0]
            : null;

        if (!cancelled) {
          setState({ status: "ready", artistId, dashboard, story });
        }
      } catch (err) {
        if (cancelled) return;
        const message = err instanceof Error ? err.message : "Failed to load studio dashboard";
        setState({ status: "error", message });
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [authReady, isAuthenticated]);

  const story = state.status === "ready" ? state.story : null;
  const dashboard = state.status === "ready" ? state.dashboard : null;
  const insightSubtext = story ? deriveInsightSubtext(story) : "";

  const difference = dashboard ? Number(dashboard.difference ?? 0) : 0;
  const differenceSign = difference > 0 ? "+" : "";
  const isNegativeDiff = dashboard ? difference < 0 : false;

  return (
    <div className="mx-auto max-w-2xl px-4 py-10">
      <header className="mb-10">
        <h1 className="text-2xl font-semibold tracking-tight">
          {studioName} Studio
        </h1>
      </header>

      {state.status === "loading" ? (
        <p className="mb-10 text-sm text-neutral-500 dark:text-neutral-400">Loading...</p>
      ) : null}

      {state.status === "error" ? (
        <p className="mb-10 text-sm text-red-600 dark:text-red-400" role="alert">
          {state.message}
        </p>
      ) : null}

      {state.status === "no_artist" ? (
        <p className="mb-10 text-sm text-neutral-500 dark:text-neutral-400">
          No artist context available for this account.
        </p>
      ) : null}

      {story ? (
        <section className="mb-10 space-y-2">
          <h2 className="text-lg font-medium text-neutral-900 dark:text-white">Insight</h2>
          <p className="text-sm text-neutral-600 dark:text-neutral-400">{story.message}</p>
          {insightSubtext ? (
            <p className="text-xs text-neutral-500 dark:text-neutral-500">{insightSubtext}</p>
          ) : null}
        </section>
      ) : null}

      <section className="mb-10 grid gap-6 sm:grid-cols-[200px_1fr] sm:gap-8">
        <div className="group relative">
          <button
            type="button"
            aria-label="Edit profile image"
            className="absolute right-2 top-2 inline-flex h-7 w-7 items-center justify-center bg-neutral-900/70 text-xs text-white opacity-0 transition-opacity duration-150 group-hover:opacity-100 dark:bg-neutral-100/80 dark:text-neutral-900"
          >
            ✎
          </button>
          <div className="aspect-square w-full bg-neutral-100 dark:bg-neutral-900" />
        </div>

        <div className="group relative space-y-2">
          <h2 className="text-lg font-medium text-neutral-900 dark:text-white">Bio</h2>
          <button
            type="button"
            aria-label="Edit bio"
            className="absolute right-0 top-0 inline-flex h-7 w-7 items-center justify-center bg-neutral-900/70 text-xs text-white opacity-0 transition-opacity duration-150 group-hover:opacity-100 dark:bg-neutral-100/80 dark:text-neutral-900"
          >
            ✎
          </button>
          <p className="text-sm text-neutral-600 dark:text-neutral-400">
            Short editorial-free description of who you are as an artist.
            Replace this with your bio text. Keep it readable and direct.
          </p>
        </div>
      </section>

      {dashboard ? (
        <section className="mb-10 space-y-4">
          <h2 className="text-lg font-medium text-neutral-900 dark:text-white">Earnings</h2>

          <div className="space-y-1">
            <p className="text-sm text-neutral-600 dark:text-neutral-400">
              <span className="font-medium text-neutral-900 dark:text-white">Total earnings:</span>{" "}
              {formatEuroAmount(dashboard.total)} €
            </p>
            <p className="text-sm text-neutral-600 dark:text-neutral-400">
              <span className="font-medium text-neutral-900 dark:text-white">Paid (on-chain):</span>{" "}
              {formatEuroAmount(dashboard.paid)} €
            </p>
            {Number(dashboard.accrued ?? 0) > 0 ? (
              <p className="text-sm text-neutral-600 dark:text-neutral-400">
                <span className="font-medium text-neutral-900 dark:text-white">
                  Accrued (not yet on-chain):
                </span>{" "}
                {formatEuroAmount(dashboard.accrued)} €
              </p>
            ) : null}
            {Number(dashboard.failed_settlement ?? 0) > 0 ? (
              <p className="text-sm text-neutral-600 dark:text-neutral-400">
                <span className="font-medium text-neutral-900 dark:text-white">
                  Settlement failed (review):
                </span>{" "}
                {formatEuroAmount(dashboard.failed_settlement)} €
              </p>
            ) : null}
            {Number(dashboard.pending ?? 0) > 0 ? (
              <p className="text-sm text-neutral-600 dark:text-neutral-400">
                <span className="font-medium text-neutral-900 dark:text-white">Pending payout:</span>{" "}
                {formatEuroAmount(dashboard.pending)} €
              </p>
            ) : null}
          </div>

          <div className="space-y-2">
            <h3 className="text-sm font-medium text-neutral-900 dark:text-white">
              Last on-chain payouts
            </h3>
            {dashboard.last_payouts.length === 0 ? (
              <p className="text-sm text-neutral-500 dark:text-neutral-400">
                No paid payouts yet.
              </p>
            ) : (
              <ul className="space-y-1">
                {dashboard.last_payouts.slice(0, 3).map((payout) => (
                  <li
                    key={`payout-${payout.batch_id}`}
                    className="text-sm text-neutral-600 dark:text-neutral-400"
                  >
                    {payout.payout_date ?? "—"} — {formatEuroAmount(payout.amount)} €
                  </li>
                ))}
              </ul>
            )}
          </div>

          <p className="text-sm text-neutral-600 dark:text-neutral-400">
            <span className="font-medium text-neutral-900 dark:text-white">Next payout:</span>{" "}
            {nextPayoutDate}
          </p>
        </section>
      ) : null}

      {dashboard ? (
        <section className="space-y-4">
          <h2 className="text-lg font-medium text-neutral-900 dark:text-white">
            Global model comparison
          </h2>

          {isNegativeDiff ? (
            <>
              <p className="text-sm leading-relaxed text-neutral-600 dark:text-neutral-400">
                Your audience is supporting you directly.
                <br />
                You are earning what&apos;s fair while contributing to a more balanced and
                sustainable music ecosystem.
                <br />
                <br />
                Thank you for inspiring the world.
              </p>
              {!showComparisonDetails ? (
                <button
                  type="button"
                  onClick={() => setShowComparisonDetails(true)}
                  className="text-sm font-medium text-neutral-900 underline-offset-4 hover:underline dark:text-white"
                >
                  See how this compares to traditional streaming platforms
                </button>
              ) : (
                <div className="space-y-1">
                  <p className="text-sm text-neutral-600 dark:text-neutral-400">
                    <span className="font-medium text-neutral-900 dark:text-white">
                      Global model estimate:
                    </span>{" "}
                    {formatEuroAmount(dashboard.spotify_total)} €
                  </p>
                  <p className="text-sm text-neutral-600 dark:text-neutral-400">
                    <span className="font-medium text-neutral-900 dark:text-white">
                      Difference:
                    </span>{" "}
                    {differenceSign}
                    {formatEuroAmount(difference)} € vs global model
                  </p>
                  <p className="pt-2 text-xs text-neutral-500 dark:text-neutral-500">
                    Comparison based on payout earnings vs global pool model (ex: Spotify, Apple
                    Music, Amazon, YouTube, etc)
                  </p>
                </div>
              )}
            </>
          ) : (
            <div className="space-y-1">
              <p className="text-sm text-neutral-600 dark:text-neutral-400">
                <span className="font-medium text-neutral-900 dark:text-white">
                  Global model estimate:
                </span>{" "}
                {formatEuroAmount(dashboard.spotify_total)} €
              </p>
              <p className="text-sm text-neutral-600 dark:text-neutral-400">
                <span className="font-medium text-neutral-900 dark:text-white">
                  You earned {differenceSign}
                  {formatEuroAmount(difference)} €
                </span>{" "}
                more than on other platforms!
              </p>
              <p className="pt-2 text-xs text-neutral-500 dark:text-neutral-500">
                Comparison based on payout earnings vs global pool model (ex: Spotify, Apple
                Music, Amazon, YouTube, etc)
              </p>
            </div>
          )}
        </section>
      ) : null}
    </div>
  );
}
