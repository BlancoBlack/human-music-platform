"use client";

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
                    <th className="px-3 py-2 text-left font-medium">Artist ID</th>
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
                      <td className="px-3 py-2">{row.artist_id}</td>
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
                    <th className="px-3 py-2 text-left font-medium">Song ID</th>
                    <th className="px-3 py-2 text-left font-medium">Artist ID</th>
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
                      <td className="px-3 py-2">{row.song_id}</td>
                      <td className="px-3 py-2">{row.artist_id ?? "—"}</td>
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
