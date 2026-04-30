"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiConflictError,
  fetchAdminActionLogs,
  fetchAdminPayouts,
  postAdminRetryBatch,
  postAdminSettleBatch,
  type AdminActionLogRow,
  type AdminPayoutFilters,
  type AdminPayoutRow,
  type AdminRetryBatchResult,
} from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

type FormFilters = {
  status: string;
  artist_id: string;
  artist_name: string;
  limit: string;
};

const STATUS_OPTIONS = ["", "pending", "processing", "accrued", "paid", "failed"];

function dash(value: string | null | undefined): string {
  const normalized = String(value || "").trim();
  return normalized ? normalized : "—";
}

function truncateMiddle(value: string, prefix = 6, suffix = 4): string {
  if (value.length <= prefix + suffix + 3) return value;
  return `${value.slice(0, prefix)}...${value.slice(-suffix)}`;
}

function statusBadgeClass(status: string): string {
  const key = (status || "").toLowerCase();
  if (key === "paid") return "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-200";
  if (key === "pending") return "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-200";
  if (key === "failed") return "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200";
  if (key === "processing")
    return "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200";
  if (key === "accrued")
    return "bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-200";
  return "bg-neutral-100 text-neutral-700 dark:bg-neutral-800 dark:text-neutral-200";
}

function formatCreated(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function formatActionLogResult(row: AdminActionLogRow): string {
  const m = row.metadata;
  if (!m || typeof m !== "object") return "—";
  const r = m as Record<string, unknown>;
  const num = (k: string): number | null =>
    typeof r[k] === "number" && Number.isFinite(r[k] as number)
      ? (r[k] as number)
      : null;
  const retried = num("retried");
  const success = num("success");
  const failed = num("failed");
  if (retried !== null && success !== null && failed !== null) {
    return `${retried} retried / ${success} success / ${failed} failed`;
  }
  if (row.action_type === "settle_batch") {
    const confirmed = num("confirmed");
    const fail = num("failed");
    const skipped = num("skipped");
    if (confirmed !== null || fail !== null || skipped !== null) {
      const parts: string[] = [];
      if (confirmed !== null) parts.push(`${confirmed} confirmed`);
      if (fail !== null) parts.push(`${fail} failed`);
      if (skipped !== null) parts.push(`${skipped} skipped`);
      return parts.length ? parts.join(" / ") : "—";
    }
  }
  return "—";
}

function InlineSpinner({ className }: { className?: string }) {
  return (
    <span
      className={`inline-block size-3 shrink-0 animate-spin rounded-full border-2 border-current border-t-transparent opacity-90 ${className ?? ""}`}
      aria-hidden
    />
  );
}

const POLL_DELAYS_MS = [4000, 6000, 10000] as const;

export default function AdminPayoutsPage() {
  const { user, authReady } = useAuth();
  const isAdmin = (user?.roles || []).includes("admin");

  const [filters, setFilters] = useState<FormFilters>({
    status: "",
    artist_id: "",
    artist_name: "",
    limit: "50",
  });
  const [rows, setRows] = useState<AdminPayoutRow[]>([]);
  const [actionLogs, setActionLogs] = useState<AdminActionLogRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadedOnce, setLoadedOnce] = useState(false);
  const [settlingBatchId, setSettlingBatchId] = useState<number | null>(null);
  const [retryingBatchId, setRetryingBatchId] = useState<number | null>(null);
  const [settleTarget, setSettleTarget] = useState<AdminPayoutRow | null>(null);
  const [settleConfirmText, setSettleConfirmText] = useState("");
  const [settleModalError, setSettleModalError] = useState<string | null>(null);
  const [retryTarget, setRetryTarget] = useState<AdminPayoutRow | null>(null);
  const [retryConfirmText, setRetryConfirmText] = useState("");
  const [retryModalError, setRetryModalError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const latestRequestIdRef = useRef(0);
  const isMountedRef = useRef(false);
  const loadRowsRef = useRef<((opts?: { soft?: boolean }) => Promise<void>) | null>(null);
  const pollingInFlightRef = useRef(false);
  const pollingCancelledRef = useRef(false);
  const pollingTimeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const parsedFilters = useMemo<AdminPayoutFilters>(() => {
    const next: AdminPayoutFilters = {};
    if (filters.status) next.status = filters.status;
    if (filters.artist_name.trim()) next.artist_name = filters.artist_name.trim();
    if (filters.artist_id.trim()) {
      const parsed = Number(filters.artist_id);
      if (Number.isFinite(parsed)) next.artist_id = parsed;
    }
    const parsedLimit = Number(filters.limit);
    if (Number.isFinite(parsedLimit)) {
      next.limit = Math.min(500, Math.max(1, parsedLimit));
    } else {
      next.limit = 50;
    }
    return next;
  }, [filters]);

  const loadRows = useCallback(async (opts?: { soft?: boolean }) => {
    const soft = opts?.soft === true;
    const requestId = ++latestRequestIdRef.current;
    if (!soft && isMountedRef.current) {
      setLoading(true);
      setError(null);
    }
    try {
      const [data, logs] = await Promise.all([
        fetchAdminPayouts(parsedFilters),
        fetchAdminActionLogs(50),
      ]);
      if (!isMountedRef.current || requestId !== latestRequestIdRef.current) {
        return;
      }
      setRows(data);
      setActionLogs(logs);
    } catch (e: unknown) {
      if (!isMountedRef.current || requestId !== latestRequestIdRef.current) {
        return;
      }
      if (soft) {
        console.warn("[admin/payouts] soft polling refresh failed", e);
        return;
      }
      setRows([]);
      setActionLogs([]);
      setError(e instanceof Error ? e.message : "Failed to load admin payouts");
    } finally {
      if (!isMountedRef.current || requestId !== latestRequestIdRef.current) {
        return;
      }
      setLoadedOnce(true);
      if (!soft) {
        setLoading(false);
      }
    }
  }, [parsedFilters]);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      pollingCancelledRef.current = true;
      if (pollingTimeoutRef.current !== undefined) {
        clearTimeout(pollingTimeoutRef.current);
      }
    };
  }, []);

  useEffect(() => {
    loadRowsRef.current = loadRows;
  }, [loadRows]);

  const hasProcessingBatch = useMemo(
    () =>
      rows.some((r) => (r.batch_status || "").toLowerCase() === "processing"),
    [rows],
  );

  useEffect(() => {
    pollingCancelledRef.current = !hasProcessingBatch;
    if (!hasProcessingBatch) {
      if (pollingTimeoutRef.current !== undefined) {
        clearTimeout(pollingTimeoutRef.current);
      }
      pollingInFlightRef.current = false;
      return;
    }

    const delays = POLL_DELAYS_MS;
    let step = 0;
    pollingCancelledRef.current = false;

    const schedule = () => {
      if (pollingCancelledRef.current) return;
      const ms = delays[Math.min(step, delays.length - 1)];
      pollingTimeoutRef.current = setTimeout(() => {
        if (pollingCancelledRef.current) return;
        if (pollingInFlightRef.current) {
          schedule();
          return;
        }
        pollingInFlightRef.current = true;
        const loader = loadRowsRef.current;
        if (!loader) {
          pollingInFlightRef.current = false;
          schedule();
          return;
        }
        void loader({ soft: true }).finally(() => {
          pollingInFlightRef.current = false;
          if (pollingCancelledRef.current) return;
          step = Math.min(step + 1, delays.length - 1);
          schedule();
        });
      }, ms);
    };

    schedule();
    return () => {
      pollingCancelledRef.current = true;
      if (pollingTimeoutRef.current !== undefined) {
        clearTimeout(pollingTimeoutRef.current);
      }
    };
  }, [hasProcessingBatch]);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    await loadRows();
  }

  useEffect(() => {
    if (!settleTarget || settlingBatchId !== null) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setSettleTarget(null);
        setSettleConfirmText("");
        setSettleModalError(null);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [settleTarget, settlingBatchId]);

  useEffect(() => {
    if (!retryTarget || retryingBatchId !== null) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setRetryTarget(null);
        setRetryConfirmText("");
        setRetryModalError(null);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [retryTarget, retryingBatchId]);

  function openSettleModal(row: AdminPayoutRow) {
    setSettleTarget(row);
    setSettleConfirmText("");
    setSettleModalError(null);
    setSuccessMessage(null);
  }

  function closeSettleModal(force = false) {
    if (!force && settlingBatchId !== null) return;
    setSettleTarget(null);
    setSettleConfirmText("");
    setSettleModalError(null);
  }

  async function onConfirmSettle() {
    if (!settleTarget || settleConfirmText !== "SETTLE") return;
    const batchId = settleTarget.batch_id;
    setSettlingBatchId(batchId);
    setError(null);
    setSettleModalError(null);
    try {
      await postAdminSettleBatch(batchId);
      closeSettleModal(true);
      setSuccessMessage(`Batch ${batchId} settled successfully.`);
      await loadRows();
    } catch (e: unknown) {
      if (e instanceof ApiConflictError) {
        closeSettleModal(true);
        setSuccessMessage(null);
        setError(e.message);
        return;
      }
      setSettleModalError(
        e instanceof Error ? e.message : `Failed to settle batch ${batchId}`,
      );
    } finally {
      setSettlingBatchId(null);
    }
  }

  function openRetryModal(row: AdminPayoutRow) {
    setRetryTarget(row);
    setRetryConfirmText("");
    setRetryModalError(null);
    setSuccessMessage(null);
  }

  function closeRetryModal(force = false) {
    if (!force && retryingBatchId !== null) return;
    setRetryTarget(null);
    setRetryConfirmText("");
    setRetryModalError(null);
  }

  async function onConfirmRetry() {
    if (!retryTarget || retryConfirmText !== "RETRY") return;
    const batchId = retryTarget.batch_id;
    setRetryingBatchId(batchId);
    setError(null);
    setRetryModalError(null);
    try {
      const summary: AdminRetryBatchResult = await postAdminRetryBatch(batchId);
      closeRetryModal(true);
      setSuccessMessage(
        `Retry completed:\n${summary.retried} retried / ${summary.success} success / ${summary.failed} failed`,
      );
      await loadRows();
    } catch (e: unknown) {
      if (e instanceof ApiConflictError) {
        closeRetryModal(true);
        setSuccessMessage(null);
        setError(e.message);
        return;
      }
      setRetryModalError(
        e instanceof Error ? e.message : `Failed to retry batch ${batchId}`,
      );
    } finally {
      setRetryingBatchId(null);
    }
  }

  if (!authReady) {
    return (
      <main className="mx-auto max-w-7xl px-4 py-8">
        <p className="text-sm text-neutral-500 dark:text-neutral-400">Loading session…</p>
      </main>
    );
  }

  if (!isAdmin) {
    return (
      <main className="mx-auto max-w-7xl px-4 py-8">
        <h1 className="text-2xl font-semibold tracking-tight">Admin Payouts</h1>
        <p
          className="mt-4 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100"
          role="alert"
        >
          Not authorized.
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-7xl px-4 py-8">
      <h1 className="text-2xl font-semibold tracking-tight">Admin Payouts</h1>
      <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
        Ledger-backed payout operations.
      </p>
      <div className="mt-3 flex items-center gap-4 text-sm">
        <Link href="/admin/discovery" className="underline">
          Discovery analytics
        </Link>
        <span className="font-medium">Payouts</span>
      </div>

      <form
        onSubmit={onSubmit}
        className="mt-6 grid grid-cols-1 gap-3 rounded-md border border-neutral-200 p-4 dark:border-neutral-800 md:grid-cols-5"
      >
        <label className="flex flex-col gap-1 text-sm">
          <span>Status</span>
          <select
            value={filters.status}
            onChange={(e) => setFilters((prev) => ({ ...prev, status: e.target.value }))}
            className="rounded border border-neutral-300 bg-white px-2 py-2 dark:border-neutral-700 dark:bg-neutral-900"
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option || "all"} value={option}>
                {option ? option.toUpperCase() : "ALL"}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1 text-sm">
          <span>Artist ID</span>
          <input
            type="number"
            inputMode="numeric"
            value={filters.artist_id}
            onChange={(e) => setFilters((prev) => ({ ...prev, artist_id: e.target.value }))}
            className="rounded border border-neutral-300 bg-white px-2 py-2 dark:border-neutral-700 dark:bg-neutral-900"
          />
        </label>

        <label className="flex flex-col gap-1 text-sm">
          <span>Artist Name</span>
          <input
            type="text"
            value={filters.artist_name}
            onChange={(e) =>
              setFilters((prev) => ({ ...prev, artist_name: e.target.value }))
            }
            className="rounded border border-neutral-300 bg-white px-2 py-2 dark:border-neutral-700 dark:bg-neutral-900"
          />
        </label>

        <label className="flex flex-col gap-1 text-sm">
          <span>Limit</span>
          <input
            type="number"
            min={1}
            max={500}
            value={filters.limit}
            onChange={(e) => setFilters((prev) => ({ ...prev, limit: e.target.value }))}
            className="rounded border border-neutral-300 bg-white px-2 py-2 dark:border-neutral-700 dark:bg-neutral-900"
          />
        </label>

        <div className="flex items-end">
          <button
            type="submit"
            disabled={loading}
            className="w-full rounded bg-neutral-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-60 dark:bg-neutral-100 dark:text-neutral-900"
          >
            {loading ? "Loading…" : "Apply filters"}
          </button>
        </div>
      </form>

      {error && (
        <p
          className="mt-4 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100"
          role="alert"
        >
          {error}
        </p>
      )}
      {successMessage && (
        <p
          className="mt-4 whitespace-pre-line rounded-md border border-green-300 bg-green-50 px-3 py-2 text-sm text-green-900 dark:border-green-800 dark:bg-green-950 dark:text-green-100"
          role="status"
        >
          {successMessage}
        </p>
      )}

      {!loadedOnce && !loading && (
        <p className="mt-6 text-sm text-neutral-500 dark:text-neutral-400">
          Apply filters to load payouts.
        </p>
      )}

      {loading && (
        <p className="mt-6 text-sm text-neutral-500 dark:text-neutral-400">Loading payouts…</p>
      )}

      {!loading && loadedOnce && rows.length === 0 && !error && (
        <p className="mt-6 text-sm text-neutral-500 dark:text-neutral-400">
          No payouts match the current filters.
        </p>
      )}

      {!loading && rows.length > 0 && (
        <div className="mt-6 overflow-x-auto rounded-md border border-neutral-200 dark:border-neutral-800">
          <table className="min-w-full text-sm">
            <thead className="bg-neutral-50 dark:bg-neutral-900/40">
              <tr>
                <th className="px-3 py-2 text-left font-medium">Batch</th>
                <th className="px-3 py-2 text-left font-medium">Users</th>
                <th className="px-3 py-2 text-left font-medium">Artist</th>
                <th className="px-3 py-2 text-right font-medium">Amount</th>
                <th className="px-3 py-2 text-left font-medium">Status</th>
                <th className="px-3 py-2 text-left font-medium">Wallet</th>
                <th className="px-3 py-2 text-left font-medium">Tx</th>
                <th className="px-3 py-2 text-left font-medium">Created</th>
                <th className="px-3 py-2 text-left font-medium">Attempts</th>
                <th className="px-3 py-2 text-left font-medium">Failure</th>
                <th className="px-3 py-2 text-left font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const tx = dash(row.tx?.tx_id ?? row.algorand_tx_id);
                const txHref =
                  row.tx?.explorer_url && String(row.tx.explorer_url).trim()
                    ? String(row.tx.explorer_url)
                    : tx !== "—"
                      ? `https://lora.algokit.io/testnet/transaction/${encodeURIComponent(tx)}`
                      : null;
                const wallet = dash(row.wallet ?? row.destination_wallet);
                const batchBusy = settlingBatchId === row.batch_id;
                const retryBusy = retryingBatchId === row.batch_id;
                const batchProcessing =
                  (row.batch_status || "").toLowerCase() === "processing";
                const canRetry = (row.batch_status || "").toLowerCase() === "failed";
                const statusLabel =
                  batchProcessing
                    ? "PROCESSING"
                    : dash(row.ui_status ?? row.status).toUpperCase();
                return (
                  <tr
                    key={row.id}
                    className="border-t border-neutral-200 align-top dark:border-neutral-800"
                  >
                    <td className="px-3 py-2">{row.batch_id}</td>
                    <td className="px-3 py-2">{row.distinct_users ?? "—"}</td>
                    <td className="px-3 py-2">
                      {row.artist_name
                        ? `${row.artist_name} (ID: ${row.artist_id})`
                        : row.artist_id}
                    </td>
                    <td className="px-3 py-2 text-right">{row.amount.toFixed(2)}</td>
                    <td className="px-3 py-2">
                      <span
                        className={`inline-flex items-center gap-1.5 rounded px-2 py-1 text-xs ${statusBadgeClass(
                          batchProcessing ? "processing" : row.ui_status ?? row.status,
                        )}`}
                      >
                        {statusLabel}
                        {batchProcessing ? <InlineSpinner /> : null}
                      </span>
                    </td>
                    <td className="max-w-[160px] truncate px-3 py-2" title={wallet}>
                      {wallet === "—" ? "—" : truncateMiddle(wallet)}
                    </td>
                    <td className="max-w-[160px] truncate px-3 py-2">
                      {txHref ? (
                        <a
                          href={txHref}
                          target="_blank"
                          rel="noreferrer"
                          className="underline"
                        >
                          {truncateMiddle(tx, 4, 4)}
                        </a>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="px-3 py-2">{formatCreated(row.created ?? row.created_at)}</td>
                    <td className="px-3 py-2">{row.attempts ?? row.attempt_count ?? "0"}</td>
                    <td className="max-w-[140px] truncate px-3 py-2" title={dash(row.failure_reason)}>
                      {dash(row.failure_reason)}
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex flex-col gap-2">
                        <button
                          type="button"
                          onClick={() => openSettleModal(row)}
                          disabled={
                            batchProcessing ||
                            batchBusy ||
                            settlingBatchId !== null ||
                            retryingBatchId !== null
                          }
                          className="rounded bg-neutral-900 px-2 py-1 text-xs font-medium text-white disabled:opacity-60 dark:bg-neutral-100 dark:text-neutral-900"
                        >
                          {batchBusy ? "Settling…" : "Settle"}
                        </button>
                        <button
                          type="button"
                          onClick={() => openRetryModal(row)}
                          disabled={
                            batchProcessing ||
                            !canRetry ||
                            retryBusy ||
                            retryingBatchId !== null ||
                            settlingBatchId !== null
                          }
                          title={
                            batchProcessing
                              ? "Wait until batch finishes processing"
                              : canRetry
                                ? "Retry failed payouts in this batch"
                                : "Only when batch status is failed"
                          }
                          className="cursor-not-allowed rounded border border-neutral-300 px-2 py-1 text-xs text-neutral-500 dark:border-neutral-700"
                        >
                          {retryBusy ? "Retrying…" : "Retry"}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {loadedOnce && !loading && (
        <section className="mt-8">
          <h2 className="text-lg font-semibold">Admin Activity</h2>
          <div className="mt-3 overflow-x-auto rounded-md border border-neutral-200 dark:border-neutral-800">
            <table className="min-w-full text-sm">
              <thead className="bg-neutral-50 dark:bg-neutral-900/40">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">Admin email</th>
                  <th className="px-3 py-2 text-left font-medium">Action</th>
                  <th className="px-3 py-2 text-left font-medium">Batch ID</th>
                  <th className="px-3 py-2 text-left font-medium">Result</th>
                  <th className="px-3 py-2 text-left font-medium">Timestamp</th>
                </tr>
              </thead>
              <tbody>
                {actionLogs.length === 0 ? (
                  <tr className="border-t border-neutral-200 dark:border-neutral-800">
                    <td className="px-3 py-2" colSpan={5}>
                      No admin actions yet.
                    </td>
                  </tr>
                ) : (
                  actionLogs.map((row, idx) => (
                    <tr
                      key={`${row.admin_user_id}-${row.target_id}-${row.created_at ?? "na"}-${idx}`}
                      className="border-t border-neutral-200 dark:border-neutral-800"
                    >
                      <td className="max-w-[200px] truncate px-3 py-2" title={dash(row.admin_user_email)}>
                        {dash(row.admin_user_email)}
                      </td>
                      <td className="px-3 py-2">{row.action_type}</td>
                      <td className="px-3 py-2">{row.target_id}</td>
                      <td className="max-w-[220px] px-3 py-2 text-xs text-neutral-700 dark:text-neutral-300">
                        {formatActionLogResult(row)}
                      </td>
                      <td className="px-3 py-2">{formatCreated(row.created_at)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>
      )}
      {settleTarget && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4"
          role="dialog"
          aria-modal="true"
          onClick={() => closeSettleModal()}
        >
          <div
            className="w-full max-w-lg rounded-lg border border-neutral-200 bg-white p-5 shadow-xl dark:border-neutral-800 dark:bg-neutral-950"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-xl font-semibold">Execute Payout</h2>
            <p className="mt-2 text-sm text-red-700 dark:text-red-300">
              You are about to execute REAL payouts. This action cannot be undone.
            </p>
            <div className="mt-4 rounded-md border border-neutral-200 p-3 text-sm dark:border-neutral-800">
              <p>
                <span className="font-medium">Batch ID:</span> {settleTarget.batch_id}
              </p>
              <p>
                <span className="font-medium">Amount:</span>{" "}
                {Number(settleTarget.amount || 0).toFixed(2)}
              </p>
            </div>

            <label htmlFor="v9m7yk" className="mt-4 block text-sm font-medium">
              Type "SETTLE" to confirm
            </label>
            <input
              id="v9m7yk"
              type="text"
              autoFocus
              value={settleConfirmText}
              onChange={(e) => setSettleConfirmText(e.target.value)}
              disabled={settlingBatchId !== null}
              className="mt-2 w-full rounded border border-neutral-300 bg-white px-3 py-2 dark:border-neutral-700 dark:bg-neutral-900"
            />

            {settleModalError && (
              <p
                className="mt-3 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100"
                role="alert"
              >
                {settleModalError}
              </p>
            )}

            <div className="mt-5 flex items-center justify-end gap-3">
              <button
                type="button"
                onClick={() => closeSettleModal()}
                disabled={settlingBatchId !== null}
                className="rounded border border-neutral-300 px-3 py-2 text-sm font-medium dark:border-neutral-700"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={onConfirmSettle}
                disabled={settleConfirmText !== "SETTLE" || settlingBatchId !== null}
                className="rounded bg-neutral-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-60 dark:bg-neutral-100 dark:text-neutral-900"
              >
                {settlingBatchId !== null ? "Executing…" : "Execute payout"}
              </button>
            </div>
          </div>
        </div>
      )}
      {retryTarget && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4"
          role="dialog"
          aria-modal="true"
          onClick={() => closeRetryModal()}
        >
          <div
            className="w-full max-w-lg rounded-lg border border-neutral-200 bg-white p-5 shadow-xl dark:border-neutral-800 dark:bg-neutral-950"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-xl font-semibold">Retry Failed Payouts</h2>
            <p className="mt-2 text-sm text-amber-700 dark:text-amber-300">
              Retry failed payouts for this batch.
            </p>
            <div className="mt-4 rounded-md border border-neutral-200 p-3 text-sm dark:border-neutral-800">
              <p>
                <span className="font-medium">Batch ID:</span> {retryTarget.batch_id}
              </p>
              <p>
                <span className="font-medium">Status:</span>{" "}
                {dash(retryTarget.ui_status ?? retryTarget.status).toUpperCase()}
              </p>
            </div>
            <label className="mt-4 block text-sm font-medium" htmlFor="retry-confirm-input">
              Type "RETRY" to confirm
            </label>
            <input
              id="retry-confirm-input"
              type="text"
              autoFocus
              value={retryConfirmText}
              onChange={(e) => setRetryConfirmText(e.target.value)}
              disabled={retryingBatchId !== null}
              className="mt-2 w-full rounded border border-neutral-300 bg-white px-3 py-2 dark:border-neutral-700 dark:bg-neutral-900"
            />
            {retryModalError && (
              <p
                className="mt-3 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100"
                role="alert"
              >
                {retryModalError}
              </p>
            )}
            <div className="mt-5 flex items-center justify-end gap-3">
              <button
                type="button"
                onClick={() => closeRetryModal()}
                disabled={retryingBatchId !== null}
                className="rounded border border-neutral-300 px-3 py-2 text-sm font-medium dark:border-neutral-700"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={onConfirmRetry}
                disabled={retryConfirmText !== "RETRY" || retryingBatchId !== null}
                className="rounded bg-neutral-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-60 dark:bg-neutral-100 dark:text-neutral-900"
              >
                {retryingBatchId !== null ? "Retrying…" : "Retry failed payouts"}
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
