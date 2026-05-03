"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  fetchDiscoveryAdminAnalytics,
  type DiscoveryAdminAnalyticsResponse,
} from "@/lib/api";

function pct(value: number): string {
  return `${(value * 100).toFixed(2)}%`;
}

export default function AdminDiscoveryPage() {
  const [data, setData] = useState<DiscoveryAdminAnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void fetchDiscoveryAdminAnalytics()
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setError(
            e instanceof Error
              ? e.message
              : "Failed to load discovery admin analytics",
          );
          setData(null);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="mx-auto max-w-6xl px-4 py-8">
      <h1 className="text-2xl font-semibold tracking-tight">
        Discovery Admin Analytics
      </h1>
      <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
        Internal, read-only telemetry aggregates.
      </p>
      <div className="mt-3 flex items-center gap-4 text-sm">
        <span className="font-medium">Discovery analytics</span>
        <Link href="/admin/payouts" className="underline">
          Payouts
        </Link>
      </div>

      {loading && (
        <p className="mt-6 text-sm text-neutral-500 dark:text-neutral-400">
          Loading analytics…
        </p>
      )}

      {error && (
        <p
          className="mt-6 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100"
          role="alert"
        >
          {error}
        </p>
      )}

      {!loading && !error && data && (
        <div className="mt-6 space-y-10">
          <section>
            <h2 className="text-lg font-semibold">Signals (read-only)</h2>
            <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
              Same windows and weighting as discovery reorder aggregation (14d, clamp,
              liked downweight). No per-user explainability — global aggregates only.
            </p>

            <h3 className="mt-4 text-sm font-semibold text-neutral-700 dark:text-neutral-200">
              Reorder ({data.signal_snapshot.reorder.window_days}d)
            </h3>
            <div className="mt-2 overflow-x-auto rounded-md border border-neutral-200 dark:border-neutral-800">
              <table className="min-w-full text-sm">
                <thead className="bg-neutral-50 dark:bg-neutral-900/40">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium">Metric</th>
                    <th className="px-3 py-2 text-right font-medium">Value</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="border-t border-neutral-200 dark:border-neutral-800">
                    <td className="px-3 py-2">Events (rows)</td>
                    <td className="px-3 py-2 text-right">
                      {data.signal_snapshot.reorder.overview.row_count.toLocaleString()}
                    </td>
                  </tr>
                  <tr className="border-t border-neutral-200 dark:border-neutral-800">
                    <td className="px-3 py-2">Distinct users</td>
                    <td className="px-3 py-2 text-right">
                      {data.signal_snapshot.reorder.overview.distinct_users.toLocaleString()}
                    </td>
                  </tr>
                  <tr className="border-t border-neutral-200 dark:border-neutral-800">
                    <td className="px-3 py-2">Distinct songs</td>
                    <td className="px-3 py-2 text-right">
                      {data.signal_snapshot.reorder.overview.distinct_songs.toLocaleString()}
                    </td>
                  </tr>
                  <tr className="border-t border-neutral-200 dark:border-neutral-800">
                    <td className="px-3 py-2">Liked playlist share of weighted sum</td>
                    <td className="px-3 py-2 text-right">
                      {pct(data.signal_snapshot.reorder.liked_share_of_weighted_sum)}
                    </td>
                  </tr>
                  <tr className="border-t border-neutral-200 dark:border-neutral-800">
                    <td className="px-3 py-2">Avg per-song weighted sum (pre–log1p cap)</td>
                    <td className="px-3 py-2 text-right">
                      {data.signal_snapshot.reorder.scale.avg_weighted_sum.toFixed(4)}
                    </td>
                  </tr>
                  <tr className="border-t border-neutral-200 dark:border-neutral-800">
                    <td className="px-3 py-2">P95 per-song weighted sum</td>
                    <td className="px-3 py-2 text-right">
                      {data.signal_snapshot.reorder.scale.p95_weighted_sum.toFixed(4)}
                    </td>
                  </tr>
                  <tr className="border-t border-neutral-200 dark:border-neutral-800">
                    <td className="px-3 py-2">
                      Top-reorder songs in 24h discovery (distinct song_ids)
                    </td>
                    <td className="px-3 py-2 text-right">
                      {pct(data.signal_snapshot.top_reorder_coverage_in_discovery)}
                    </td>
                  </tr>
                  <tr className="border-t border-neutral-200 dark:border-neutral-800">
                    <td className="px-3 py-2">
                      Likes ↔ reorder overlap (|top50 ∩ top50| / |top50 reorder|)
                    </td>
                    <td className="px-3 py-2 text-right">
                      {pct(data.signal_snapshot.likes_reorder_overlap)}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <h3 className="mt-4 text-sm font-semibold text-neutral-700 dark:text-neutral-200">
              Per-song weighted sum (histogram)
            </h3>
            <div className="mt-2 overflow-x-auto rounded-md border border-neutral-200 dark:border-neutral-800">
              <table className="min-w-full text-sm">
                <thead className="bg-neutral-50 dark:bg-neutral-900/40">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium">Bucket</th>
                    <th className="px-3 py-2 text-right font-medium">Song count</th>
                  </tr>
                </thead>
                <tbody>
                  {data.signal_snapshot.reorder.per_song_weighted_histogram.map((row) => (
                    <tr
                      key={row.bucket}
                      className="border-t border-neutral-200 dark:border-neutral-800"
                    >
                      <td className="px-3 py-2">{row.bucket}</td>
                      <td className="px-3 py-2 text-right">{row.song_count.toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <h3 className="mt-4 text-sm font-semibold text-neutral-700 dark:text-neutral-200">
              Top reorder songs (by weighted sum)
            </h3>
            <div className="mt-2 max-h-64 overflow-y-auto overflow-x-auto rounded-md border border-neutral-200 dark:border-neutral-800">
              <table className="min-w-full text-sm">
                <thead className="sticky top-0 bg-neutral-50 dark:bg-neutral-900/40">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium">Song</th>
                    <th className="px-3 py-2 text-left font-medium">Artist</th>
                    <th className="px-3 py-2 text-right font-medium">Weighted sum</th>
                    <th className="px-3 py-2 text-right font-medium">Events</th>
                  </tr>
                </thead>
                <tbody>
                  {data.signal_snapshot.reorder.top_reorder_songs.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="px-3 py-2 text-neutral-500">
                        No reorder events in window.
                      </td>
                    </tr>
                  ) : (
                    data.signal_snapshot.reorder.top_reorder_songs.map((row) => (
                      <tr
                        key={row.song_id}
                        className="border-t border-neutral-200 dark:border-neutral-800"
                      >
                        <td className="px-3 py-2">
                          <span className="text-neutral-500">#{row.song_id}</span>{" "}
                          {row.title}
                        </td>
                        <td className="px-3 py-2">{row.artist_name}</td>
                        <td className="px-3 py-2 text-right">{row.weighted_sum}</td>
                        <td className="px-3 py-2 text-right">{row.event_count}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            <h3 className="mt-6 text-sm font-semibold text-neutral-700 dark:text-neutral-200">
              Likes ({data.signal_snapshot.likes.window_days}d)
            </h3>
            <div className="mt-2 overflow-x-auto rounded-md border border-neutral-200 dark:border-neutral-800">
              <table className="min-w-full text-sm">
                <thead className="bg-neutral-50 dark:bg-neutral-900/40">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium">Metric</th>
                    <th className="px-3 py-2 text-right font-medium">Value</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="border-t border-neutral-200 dark:border-neutral-800">
                    <td className="px-3 py-2">Total like events</td>
                    <td className="px-3 py-2 text-right">
                      {data.signal_snapshot.likes.overview.total_events.toLocaleString()}
                    </td>
                  </tr>
                  <tr className="border-t border-neutral-200 dark:border-neutral-800">
                    <td className="px-3 py-2">Distinct users</td>
                    <td className="px-3 py-2 text-right">
                      {data.signal_snapshot.likes.overview.distinct_users.toLocaleString()}
                    </td>
                  </tr>
                  <tr className="border-t border-neutral-200 dark:border-neutral-800">
                    <td className="px-3 py-2">Distinct songs</td>
                    <td className="px-3 py-2 text-right">
                      {data.signal_snapshot.likes.overview.distinct_songs.toLocaleString()}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <h3 className="mt-4 text-sm font-semibold text-neutral-700 dark:text-neutral-200">
              Top liked songs
            </h3>
            <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
              Counts use the same <strong>matured</strong> window as ranking likes (≥{" "}
              {data.signal_snapshot.likes.ranking_context.maturity_minutes} min old, within{" "}
              {data.signal_snapshot.likes.window_days}d).
            </p>
            <div className="mt-2 max-h-64 overflow-y-auto overflow-x-auto rounded-md border border-neutral-200 dark:border-neutral-800">
              <table className="min-w-full text-sm">
                <thead className="sticky top-0 bg-neutral-50 dark:bg-neutral-900/40">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium">Song</th>
                    <th className="px-3 py-2 text-left font-medium">Artist</th>
                    <th className="px-3 py-2 text-right font-medium">Likes</th>
                  </tr>
                </thead>
                <tbody>
                  {data.signal_snapshot.likes.top_liked_songs.length === 0 ? (
                    <tr>
                      <td colSpan={3} className="px-3 py-2 text-neutral-500">
                        No likes in window.
                      </td>
                    </tr>
                  ) : (
                    data.signal_snapshot.likes.top_liked_songs.map((row) => (
                      <tr
                        key={row.song_id}
                        className="border-t border-neutral-200 dark:border-neutral-800"
                      >
                        <td className="px-3 py-2">
                          <span className="text-neutral-500">#{row.song_id}</span>{" "}
                          {row.title}
                        </td>
                        <td className="px-3 py-2">{row.artist ?? row.artist_name}</td>
                        <td className="px-3 py-2 text-right">{row.count}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            <h3 className="mt-6 text-sm font-semibold text-neutral-700 dark:text-neutral-200">
              Likes signal distribution (ranking sample)
            </h3>
            <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
              Up to {data.signal_snapshot.likes.ranking_context.sample_songs.toLocaleString()} songs
              with the most matured likes; signals match{" "}
              <code className="rounded bg-neutral-100 px-1 dark:bg-neutral-800">
                compute_signal_contributions
              </code>{" "}
              (reorder=0). Cap enabled:{" "}
              {data.signal_snapshot.likes.ranking_context.like_cap_enabled ? "yes" : "no"}, cap{" "}
              {data.signal_snapshot.likes.ranking_context.like_cap}, playlist↔like damp{" "}
              {data.signal_snapshot.likes.ranking_context.playlist_like_correlation_damp}.
            </p>
            <div className="mt-2 grid gap-4 sm:grid-cols-2">
              <div className="overflow-x-auto rounded-md border border-neutral-200 dark:border-neutral-800">
                <table className="min-w-full text-sm">
                  <thead className="bg-neutral-50 dark:bg-neutral-900/40">
                    <tr>
                      <th className="px-3 py-2 text-left font-medium">like_signal bin</th>
                      <th className="px-3 py-2 text-right font-medium">Songs</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.signal_snapshot.likes.ranking_context.like_signal_histogram.map(
                      (row) => (
                        <tr
                          key={row.bucket}
                          className="border-t border-neutral-200 dark:border-neutral-800"
                        >
                          <td className="px-3 py-2">{row.bucket}</td>
                          <td className="px-3 py-2 text-right">
                            {row.song_count.toLocaleString()}
                          </td>
                        </tr>
                      ),
                    )}
                  </tbody>
                </table>
              </div>
              <div className="overflow-x-auto rounded-md border border-neutral-200 dark:border-neutral-800">
                <table className="min-w-full text-sm">
                  <thead className="bg-neutral-50 dark:bg-neutral-900/40">
                    <tr>
                      <th className="px-3 py-2 text-left font-medium">like_boost bin</th>
                      <th className="px-3 py-2 text-right font-medium">Songs</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.signal_snapshot.likes.ranking_context.like_boost_histogram.map(
                      (row) => (
                        <tr
                          key={row.bucket}
                          className="border-t border-neutral-200 dark:border-neutral-800"
                        >
                          <td className="px-3 py-2">{row.bucket}</td>
                          <td className="px-3 py-2 text-right">
                            {row.song_count.toLocaleString()}
                          </td>
                        </tr>
                      ),
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            <h3 className="mt-6 text-sm font-semibold text-neutral-700 dark:text-neutral-200">
              Playlist ↔ like correlation (sample)
            </h3>
            <div className="mt-2 overflow-x-auto rounded-md border border-neutral-200 dark:border-neutral-800">
              <table className="min-w-full text-sm">
                <thead className="bg-neutral-50 dark:bg-neutral-900/40">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium">Metric</th>
                    <th className="px-3 py-2 text-right font-medium">Value</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="border-t border-neutral-200 dark:border-neutral-800">
                    <td className="px-3 py-2">Avg like_signal</td>
                    <td className="px-3 py-2 text-right">
                      {data.signal_snapshot.likes.ranking_context.correlation.avg_like_signal.toFixed(
                        4,
                      )}
                    </td>
                  </tr>
                  <tr className="border-t border-neutral-200 dark:border-neutral-800">
                    <td className="px-3 py-2">Avg playlist_signal</td>
                    <td className="px-3 py-2 text-right">
                      {data.signal_snapshot.likes.ranking_context.correlation.avg_playlist_signal.toFixed(
                        4,
                      )}
                    </td>
                  </tr>
                  <tr className="border-t border-neutral-200 dark:border-neutral-800">
                    <td className="px-3 py-2">% sample songs with like + playlist</td>
                    <td className="px-3 py-2 text-right">
                      {pct(data.signal_snapshot.likes.ranking_context.correlation.pct_songs_with_like_and_playlist)}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <h3 className="mt-6 text-sm font-semibold text-neutral-700 dark:text-neutral-200">
              Avg signal contributions (global sample, reorder N/A)
            </h3>
            <div className="mt-2 overflow-x-auto rounded-md border border-neutral-200 dark:border-neutral-800">
              <table className="min-w-full text-sm">
                <thead className="bg-neutral-50 dark:bg-neutral-900/40">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium">Signal</th>
                    <th className="px-3 py-2 text-right font-medium">Avg contribution</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="border-t border-neutral-200 dark:border-neutral-800">
                    <td className="px-3 py-2">Playlist</td>
                    <td className="px-3 py-2 text-right">
                      {data.signal_snapshot.likes.ranking_context.avg_contributions.playlist_boost.toFixed(
                        6,
                      )}
                    </td>
                  </tr>
                  <tr className="border-t border-neutral-200 dark:border-neutral-800">
                    <td className="px-3 py-2">Likes</td>
                    <td className="px-3 py-2 text-right">
                      {data.signal_snapshot.likes.ranking_context.avg_contributions.like_boost.toFixed(
                        6,
                      )}
                    </td>
                  </tr>
                  <tr className="border-t border-neutral-200 dark:border-neutral-800">
                    <td className="px-3 py-2">Reorder</td>
                    <td className="px-3 py-2 text-right text-neutral-500">
                      {data.signal_snapshot.likes.ranking_context.avg_contributions.reorder_boost ??
                        "—"}
                    </td>
                  </tr>
                </tbody>
              </table>
              <p className="border-t border-neutral-200 px-3 py-2 text-xs text-neutral-500 dark:border-neutral-800 dark:text-neutral-400">
                {data.signal_snapshot.likes.ranking_context.avg_contributions.reorder_note}
              </p>
            </div>
          </section>

          <section>
            <h2 className="text-lg font-semibold">1) CTR by section</h2>
            <div className="mt-3 overflow-x-auto rounded-md border border-neutral-200 dark:border-neutral-800">
              <table className="min-w-full text-sm">
                <thead className="bg-neutral-50 dark:bg-neutral-900/40">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium">Section</th>
                    <th className="px-3 py-2 text-right font-medium">Impressions</th>
                    <th className="px-3 py-2 text-right font-medium">Clicks</th>
                    <th className="px-3 py-2 text-right font-medium">CTR</th>
                  </tr>
                </thead>
                <tbody>
                  {data.ctr_by_section.map((row) => (
                    <tr
                      key={row.section}
                      className="border-t border-neutral-200 dark:border-neutral-800"
                    >
                      <td className="px-3 py-2">{row.section}</td>
                      <td className="px-3 py-2 text-right">
                        {row.impressions.toLocaleString()}
                      </td>
                      <td className="px-3 py-2 text-right">
                        {row.clicks.toLocaleString()}
                      </td>
                      <td className="px-3 py-2 text-right">{pct(row.ctr)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section>
            <h2 className="text-lg font-semibold">2) CTR by position</h2>
            <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
              Chart-ready rows (position, impressions, clicks, ctr).
            </p>
            <div className="mt-3 overflow-x-auto rounded-md border border-neutral-200 dark:border-neutral-800">
              <table className="min-w-full text-sm">
                <thead className="bg-neutral-50 dark:bg-neutral-900/40">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium">Global position</th>
                    <th className="px-3 py-2 text-right font-medium">Impressions</th>
                    <th className="px-3 py-2 text-right font-medium">Clicks</th>
                    <th className="px-3 py-2 text-right font-medium">CTR</th>
                  </tr>
                </thead>
                <tbody>
                  {data.ctr_by_position.map((row) => (
                    <tr
                      key={row.global_position}
                      className="border-t border-neutral-200 dark:border-neutral-800"
                    >
                      <td className="px-3 py-2">{row.global_position}</td>
                      <td className="px-3 py-2 text-right">
                        {row.impressions.toLocaleString()}
                      </td>
                      <td className="px-3 py-2 text-right">
                        {row.clicks.toLocaleString()}
                      </td>
                      <td className="px-3 py-2 text-right">{pct(row.ctr)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section>
            <h2 className="text-lg font-semibold">3) Candidate pool performance</h2>
            <div className="mt-3 overflow-x-auto rounded-md border border-neutral-200 dark:border-neutral-800">
              <table className="min-w-full text-sm">
                <thead className="bg-neutral-50 dark:bg-neutral-900/40">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium">Pool</th>
                    <th className="px-3 py-2 text-right font-medium">Impressions</th>
                    <th className="px-3 py-2 text-right font-medium">Clicks</th>
                    <th className="px-3 py-2 text-right font-medium">CTR</th>
                  </tr>
                </thead>
                <tbody>
                  {data.candidate_pool_performance.map((row) => (
                    <tr
                      key={row.candidate_pool}
                      className="border-t border-neutral-200 dark:border-neutral-800"
                    >
                      <td className="px-3 py-2">{row.candidate_pool}</td>
                      <td className="px-3 py-2 text-right">
                        {row.impressions.toLocaleString()}
                      </td>
                      <td className="px-3 py-2 text-right">
                        {row.clicks.toLocaleString()}
                      </td>
                      <td className="px-3 py-2 text-right">{pct(row.ctr)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section>
            <h2 className="text-lg font-semibold">4) Candidate pool by section</h2>
            <div className="mt-3 overflow-x-auto rounded-md border border-neutral-200 dark:border-neutral-800">
              <table className="min-w-full text-sm">
                <thead className="bg-neutral-50 dark:bg-neutral-900/40">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium">Section</th>
                    <th className="px-3 py-2 text-left font-medium">Pool</th>
                    <th className="px-3 py-2 text-right font-medium">Impressions</th>
                    <th className="px-3 py-2 text-right font-medium">CTR</th>
                    <th className="px-3 py-2 text-right font-medium">Share in section</th>
                  </tr>
                </thead>
                <tbody>
                  {data.candidate_pool_by_section.map((row) => (
                    <tr
                      key={`${row.section}-${row.candidate_pool}`}
                      className="border-t border-neutral-200 dark:border-neutral-800"
                    >
                      <td className="px-3 py-2">{row.section}</td>
                      <td className="px-3 py-2">{row.candidate_pool}</td>
                      <td className="px-3 py-2 text-right">
                        {row.impressions.toLocaleString()}
                      </td>
                      <td className="px-3 py-2 text-right">{pct(row.ctr)}</td>
                      <td className="px-3 py-2 text-right">{pct(row.share)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section>
            <h2 className="text-lg font-semibold">5) CTR by ranking version</h2>
            <div className="mt-3 overflow-x-auto rounded-md border border-neutral-200 dark:border-neutral-800">
              <table className="min-w-full text-sm">
                <thead className="bg-neutral-50 dark:bg-neutral-900/40">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium">Ranking version</th>
                    <th className="px-3 py-2 text-right font-medium">Impressions</th>
                    <th className="px-3 py-2 text-right font-medium">Clicks</th>
                    <th className="px-3 py-2 text-right font-medium">CTR</th>
                  </tr>
                </thead>
                <tbody>
                  {data.ctr_by_ranking_version.map((row) => (
                    <tr
                      key={row.ranking_version}
                      className="border-t border-neutral-200 dark:border-neutral-800"
                    >
                      <td className="px-3 py-2">{row.ranking_version}</td>
                      <td className="px-3 py-2 text-right">
                        {row.impressions.toLocaleString()}
                      </td>
                      <td className="px-3 py-2 text-right">
                        {row.clicks.toLocaleString()}
                      </td>
                      <td className="px-3 py-2 text-right">{pct(row.ctr)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section>
            <h2 className="text-lg font-semibold">6) Top artists concentration</h2>
            <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-300">
              Top artists share:{" "}
              <span className="font-medium">
                {pct(data.top_artists_concentration.top_artists_share)}
              </span>{" "}
              of {data.top_artists_concentration.total_impressions.toLocaleString()} total
              impressions.
            </p>
            <div className="mt-3 overflow-x-auto rounded-md border border-neutral-200 dark:border-neutral-800">
              <table className="min-w-full text-sm">
                <thead className="bg-neutral-50 dark:bg-neutral-900/40">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium">Artist</th>
                    <th className="px-3 py-2 text-right font-medium">Impressions</th>
                    <th className="px-3 py-2 text-right font-medium">Share</th>
                  </tr>
                </thead>
                <tbody>
                  {data.top_artists_concentration.top_artists.map((row) => (
                    <tr
                      key={row.artist_id}
                      className="border-t border-neutral-200 dark:border-neutral-800"
                    >
                      <td className="px-3 py-2">
                        <span className="text-neutral-500">#{row.artist_id}</span>{" "}
                        {row.artist_name ?? "—"}
                      </td>
                      <td className="px-3 py-2 text-right">
                        {row.impressions.toLocaleString()}
                      </td>
                      <td className="px-3 py-2 text-right">{pct(row.share)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section>
            <h2 className="text-lg font-semibold">7) High-score / low-CTR anomalies</h2>
            <div className="mt-3 overflow-x-auto rounded-md border border-neutral-200 dark:border-neutral-800">
              <table className="min-w-full text-sm">
                <thead className="bg-neutral-50 dark:bg-neutral-900/40">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium">Song</th>
                    <th className="px-3 py-2 text-left font-medium">Artist</th>
                    <th className="px-3 py-2 text-right font-medium">Avg score (play_now)</th>
                    <th className="px-3 py-2 text-right font-medium">Impressions</th>
                    <th className="px-3 py-2 text-right font-medium">Clicks</th>
                    <th className="px-3 py-2 text-right font-medium">CTR</th>
                  </tr>
                </thead>
                <tbody>
                  {data.high_score_low_ctr_anomalies.map((row) => (
                    <tr
                      key={`${row.song_id}-${row.artist_id ?? "na"}`}
                      className="border-t border-neutral-200 dark:border-neutral-800"
                    >
                      <td className="px-3 py-2">
                        <span className="text-neutral-500">#{row.song_id}</span>{" "}
                        {row.song_title ?? "—"}
                      </td>
                      <td className="px-3 py-2">
                        {row.artist_id != null ? (
                          <>
                            <span className="text-neutral-500">#{row.artist_id}</span>{" "}
                            {row.artist_name ?? "—"}
                          </>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="px-3 py-2 text-right">
                        {row.avg_score_play_now.toFixed(3)}
                      </td>
                      <td className="px-3 py-2 text-right">
                        {row.impressions.toLocaleString()}
                      </td>
                      <td className="px-3 py-2 text-right">
                        {row.clicks.toLocaleString()}
                      </td>
                      <td className="px-3 py-2 text-right">{pct(row.ctr)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section>
            <h2 className="text-lg font-semibold">8) Diversity per request (24h)</h2>
            <div className="mt-3 overflow-x-auto rounded-md border border-neutral-200 dark:border-neutral-800">
              <table className="min-w-full text-sm">
                <thead className="bg-neutral-50 dark:bg-neutral-900/40">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium">Metric</th>
                    <th className="px-3 py-2 text-right font-medium">Value</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="border-t border-neutral-200 dark:border-neutral-800">
                    <td className="px-3 py-2">Avg unique artists / request</td>
                    <td className="px-3 py-2 text-right">
                      {data.diversity_per_request.avg_unique_artists.toFixed(2)}
                    </td>
                  </tr>
                  <tr className="border-t border-neutral-200 dark:border-neutral-800">
                    <td className="px-3 py-2">Min unique artists / request</td>
                    <td className="px-3 py-2 text-right">
                      {data.diversity_per_request.min_unique_artists}
                    </td>
                  </tr>
                  <tr className="border-t border-neutral-200 dark:border-neutral-800">
                    <td className="px-3 py-2">Max unique artists / request</td>
                    <td className="px-3 py-2 text-right">
                      {data.diversity_per_request.max_unique_artists}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          <section>
            <h2 className="text-lg font-semibold">9) Score vs CTR buckets (ranking drift)</h2>
            <div className="mt-3 overflow-x-auto rounded-md border border-neutral-200 dark:border-neutral-800">
              <table className="min-w-full text-sm">
                <thead className="bg-neutral-50 dark:bg-neutral-900/40">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium">Score bucket</th>
                    <th className="px-3 py-2 text-right font-medium">Impressions</th>
                    <th className="px-3 py-2 text-right font-medium">Clicks</th>
                    <th className="px-3 py-2 text-right font-medium">CTR</th>
                  </tr>
                </thead>
                <tbody>
                  {data.score_ctr_correlation.map((row) => (
                    <tr
                      key={row.bucket}
                      className="border-t border-neutral-200 dark:border-neutral-800"
                    >
                      <td className="px-3 py-2">{row.bucket}</td>
                      <td className="px-3 py-2 text-right">
                        {row.impressions.toLocaleString()}
                      </td>
                      <td className="px-3 py-2 text-right">
                        {row.clicks.toLocaleString()}
                      </td>
                      <td className="px-3 py-2 text-right">{pct(row.ctr)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      )}
    </main>
  );
}
