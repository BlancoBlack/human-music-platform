"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  fetchStudioArtistAnalytics,
  fetchStudioMe,
  type StudioArtistAnalyticsResponse,
} from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

const RANGE_OPTIONS = [
  { value: "last_day", label: "Last day" },
  { value: "last_week", label: "Last week" },
  { value: "last_30_days", label: "Last 30 days" },
  { value: "last_3_months", label: "Last 3 months" },
] as const;

type RangeValue = (typeof RANGE_OPTIONS)[number]["value"];

type ArtistOption = { id: number; name: string };

function StreamsLineChart({ streams }: { streams: Record<string, number> }) {
  const chartData = useMemo(
    () =>
      Object.entries(streams)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([date, value]) => ({
          date,
          streams: Number(value) || 0,
        })),
    [streams],
  );

  if (chartData.length === 0) {
    return (
      <p className="text-sm text-neutral-500 dark:text-neutral-400">Not enough data yet</p>
    );
  }

  return (
    <div className="h-[280px] w-full min-w-0">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart
          data={chartData}
          margin={{ top: 8, right: 12, left: 0, bottom: 8 }}
        >
          <CartesianGrid
            strokeDasharray="3 3"
            className="stroke-neutral-200 dark:stroke-neutral-700"
          />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 11, fill: "currentColor" }}
            className="text-neutral-500"
            interval="preserveStartEnd"
            angle={chartData.length > 10 ? -30 : 0}
            textAnchor={chartData.length > 10 ? "end" : "middle"}
            height={chartData.length > 10 ? 56 : 28}
          />
          <YAxis
            tick={{ fontSize: 11, fill: "currentColor" }}
            className="text-neutral-500"
            allowDecimals={false}
            width={48}
          />
          <Tooltip
            contentStyle={{
              borderRadius: "0.5rem",
              border: "1px solid rgb(229 229 229)",
              fontSize: "0.875rem",
            }}
            labelStyle={{ fontWeight: 600 }}
          />
          <Line
            type="monotone"
            dataKey="streams"
            name="Streams"
            stroke="#60a5fa"
            strokeWidth={2}
            dot={{ r: 3, fill: "#60a5fa" }}
            activeDot={{ r: 5 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function StudioAnalyticsPage() {
  const { authReady, isAuthenticated } = useAuth();
  const [range, setRange] = useState<RangeValue>("last_30_days");

  const [meLoading, setMeLoading] = useState(true);
  const [meError, setMeError] = useState<string | null>(null);
  const [artists, setArtists] = useState<ArtistOption[]>([]);
  const [selectedArtistId, setSelectedArtistId] = useState<number | null>(null);

  const [data, setData] = useState<StudioArtistAnalyticsResponse | null>(null);
  const [dataLoading, setDataLoading] = useState(false);
  const [dataError, setDataError] = useState<string | null>(null);

  useEffect(() => {
    if (!authReady) return;
    if (!isAuthenticated) {
      queueMicrotask(() => {
        setMeLoading(false);
        setMeError(null);
        setArtists([]);
        setSelectedArtistId(null);
      });
      return;
    }

    let cancelled = false;
    queueMicrotask(() => {
      setMeLoading(true);
      setMeError(null);
    });

    void (async () => {
      try {
        const me = await fetchStudioMe();
        if (cancelled) return;
        const list: ArtistOption[] = (me.allowed_contexts?.artists ?? []).map((a) => ({
          id: Number(a.id),
          name: String(a.name ?? "").trim() || `Artist ${a.id}`,
        }));
        setArtists(list);
        setSelectedArtistId((prev) => {
          if (list.length === 0) return null;
          if (prev !== null && list.some((x) => x.id === prev)) return prev;
          const ctx =
            me.current_context?.type === "artist" ? Number(me.current_context.id) : null;
          if (ctx !== null && list.some((x) => x.id === ctx)) return ctx;
          return list[0].id;
        });
      } catch (err) {
        if (!cancelled) {
          setMeError(err instanceof Error ? err.message : "Failed to load studio context");
          setArtists([]);
          setSelectedArtistId(null);
        }
      } finally {
        if (!cancelled) setMeLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [authReady, isAuthenticated]);

  useEffect(() => {
    if (!authReady || !isAuthenticated) return;
    if (selectedArtistId == null || artists.length === 0) return;

    let cancelled = false;
    queueMicrotask(() => setDataLoading(true));

    void (async () => {
      try {
        const next = await fetchStudioArtistAnalytics(selectedArtistId, range);
        if (!cancelled) {
          setData(next);
          setDataError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setDataError(err instanceof Error ? err.message : "Failed to load analytics");
        }
      } finally {
        if (!cancelled) setDataLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [authReady, isAuthenticated, selectedArtistId, range, artists.length]);

  if (!authReady || !isAuthenticated) {
    return (
      <section className="mx-auto max-w-4xl space-y-6">
        <h1 className="text-2xl font-semibold tracking-tight">Analytics</h1>
        <p className="text-sm text-neutral-500 dark:text-neutral-400">Loading analytics...</p>
      </section>
    );
  }

  if (meLoading) {
    return (
      <section className="mx-auto max-w-4xl space-y-6">
        <h1 className="text-2xl font-semibold tracking-tight">Analytics</h1>
        <p className="text-sm text-neutral-500 dark:text-neutral-400">Loading analytics...</p>
      </section>
    );
  }

  if (meError) {
    return (
      <section className="mx-auto max-w-4xl space-y-6">
        <h1 className="text-2xl font-semibold tracking-tight">Analytics</h1>
        <p className="text-sm text-red-600 dark:text-red-400" role="alert">
          {meError}
        </p>
      </section>
    );
  }

  if (artists.length === 0 || selectedArtistId == null) {
    return (
      <section className="mx-auto max-w-4xl space-y-6">
        <h1 className="text-2xl font-semibold tracking-tight">Analytics</h1>
        <p className="text-sm text-neutral-500 dark:text-neutral-400">
          No artist context available for this account.
        </p>
      </section>
    );
  }

  if (dataError && !data) {
    return (
      <section className="mx-auto max-w-4xl space-y-6">
        <h1 className="text-2xl font-semibold tracking-tight">Analytics</h1>
        <label className="flex max-w-xs flex-col gap-1 text-sm">
          <span className="font-medium text-neutral-700 dark:text-neutral-300">Artist</span>
          <select
            className="rounded-md border border-neutral-300 bg-white px-3 py-2 text-neutral-900 dark:border-neutral-700 dark:bg-neutral-950 dark:text-neutral-100"
            value={selectedArtistId}
            onChange={(e) => {
              setData(null);
              setDataError(null);
              setSelectedArtistId(Number(e.target.value));
            }}
          >
            {artists.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        </label>
        <p className="text-sm text-red-600 dark:text-red-400" role="alert">
          {dataError}
        </p>
      </section>
    );
  }

  const payload = data;
  const totalSongStreams =
    payload?.top_songs.reduce((acc, row) => acc + Number(row.streams || 0), 0) ?? 0;

  return (
    <section className="mx-auto max-w-4xl space-y-8">
      <header className="flex flex-col gap-4">
        <h1 className="text-2xl font-semibold tracking-tight">Analytics</h1>
        <div className="flex flex-col gap-4 sm:flex-row sm:flex-wrap sm:items-end">
          <label className="flex min-w-[200px] flex-col gap-1 text-sm">
            <span className="font-medium text-neutral-700 dark:text-neutral-300">Artist</span>
            <select
              className="rounded-md border border-neutral-300 bg-white px-3 py-2 text-neutral-900 dark:border-neutral-700 dark:bg-neutral-950 dark:text-neutral-100"
              value={selectedArtistId}
              onChange={(e) => {
                setData(null);
                setDataError(null);
                setSelectedArtistId(Number(e.target.value));
              }}
            >
              {artists.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex min-w-[200px] flex-col gap-1 text-sm">
            <span className="font-medium text-neutral-700 dark:text-neutral-300">Range</span>
            <select
              className="rounded-md border border-neutral-300 bg-white px-3 py-2 text-neutral-900 dark:border-neutral-700 dark:bg-neutral-950 dark:text-neutral-100"
              value={range}
              onChange={(e) => setRange(e.target.value as RangeValue)}
            >
              {RANGE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </label>
        </div>
        {dataLoading ? (
          <p className="text-sm text-neutral-500 dark:text-neutral-400">Updating analytics…</p>
        ) : null}
        {dataError && data ? (
          <p className="text-sm text-amber-700 dark:text-amber-300" role="status">
            Could not refresh: {dataError}. Showing previous data.
          </p>
        ) : null}
      </header>

      {!payload ? (
        <p className="text-sm text-neutral-500 dark:text-neutral-400">Loading analytics...</p>
      ) : (
        <>
          <section className="rounded-lg border border-neutral-200 bg-white p-5 dark:border-neutral-800 dark:bg-neutral-950">
            <h2 className="mb-4 text-lg font-medium text-neutral-900 dark:text-neutral-100">
              Streams
            </h2>
            <StreamsLineChart streams={payload.streams} />
          </section>

          <section className="rounded-lg border border-neutral-200 bg-white p-5 dark:border-neutral-800 dark:bg-neutral-950">
            <h2 className="mb-4 text-lg font-medium text-neutral-900 dark:text-neutral-100">
              Top songs
            </h2>
            {payload.top_songs.length === 0 ? (
              <p className="text-sm text-neutral-500 dark:text-neutral-400">
                Not enough data yet
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[320px] text-left text-sm">
                  <thead>
                    <tr className="border-b border-neutral-200 dark:border-neutral-800">
                      <th className="pb-2 pr-4 font-medium text-neutral-700 dark:text-neutral-300">
                        Title
                      </th>
                      <th className="pb-2 pr-4 font-medium text-neutral-700 dark:text-neutral-300">
                        Streams
                      </th>
                      <th className="pb-2 font-medium text-neutral-700 dark:text-neutral-300">
                        % of total
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {payload.top_songs.map((row) => {
                      const streams = Number(row.streams || 0);
                      const pct =
                        totalSongStreams > 0
                          ? ((streams / totalSongStreams) * 100).toFixed(1)
                          : "0.0";
                      return (
                        <tr
                          key={row.song_id}
                          className="border-b border-neutral-100 dark:border-neutral-900"
                        >
                          <td className="py-2 pr-4 text-neutral-900 dark:text-neutral-100">
                            {row.title}
                          </td>
                          <td className="py-2 pr-4 tabular-nums text-neutral-700 dark:text-neutral-300">
                            {streams}
                          </td>
                          <td className="py-2 tabular-nums text-neutral-700 dark:text-neutral-300">
                            {pct}%
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="rounded-lg border border-neutral-200 bg-white p-5 dark:border-neutral-800 dark:bg-neutral-950">
            <h2 className="mb-4 text-lg font-medium text-neutral-900 dark:text-neutral-100">
              Top fans
            </h2>
            {payload.top_fans.length === 0 ? (
              <p className="text-sm text-neutral-500 dark:text-neutral-400">
                Not enough data yet
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[360px] text-left text-sm">
                  <thead>
                    <tr className="border-b border-neutral-200 dark:border-neutral-800">
                      <th className="pb-2 pr-4 font-medium text-neutral-700 dark:text-neutral-300">
                        Username
                      </th>
                      <th className="pb-2 pr-4 font-medium text-neutral-700 dark:text-neutral-300">
                        Total streams
                      </th>
                      <th className="pb-2 font-medium text-neutral-700 dark:text-neutral-300">
                        Favorite song
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {payload.top_fans.map((row) => {
                      const top = row.top_song;
                      const songTitle =
                        top.title != null && String(top.title).trim() !== ""
                          ? String(top.title)
                          : "—";
                      const songStreams = Number(top.streams || 0);
                      return (
                        <tr
                          key={row.user_id}
                          className="border-b border-neutral-100 dark:border-neutral-900 align-top"
                        >
                          <td className="py-2 pr-4 font-medium text-neutral-900 dark:text-neutral-100">
                            {row.username}
                          </td>
                          <td className="py-2 pr-4 tabular-nums text-neutral-700 dark:text-neutral-300">
                            {Number(row.streams || 0)}
                          </td>
                          <td className="py-2 text-neutral-700 dark:text-neutral-300">
                            <span>{songTitle}</span>
                            <span className="text-neutral-500 dark:text-neutral-500">
                              {" "}
                              ({songStreams} streams)
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </section>
  );
}
