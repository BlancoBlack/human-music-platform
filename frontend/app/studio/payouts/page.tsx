"use client";

import { useEffect, useRef, useState } from "react";
import {
  fetchStudioArtistPayouts,
  fetchStudioMe,
  postStudioArtistPayoutMethod,
  type StudioArtistPayoutsResponse,
  type StudioPayoutHistoryRow,
} from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

type PayoutState =
  | { status: "idle" | "loading" }
  | { status: "no_artist" }
  | { status: "error"; message: string }
  | { status: "ready"; artistId: number; payouts: StudioArtistPayoutsResponse };

function formatEur(value: number): string {
  return new Intl.NumberFormat("en-IE", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(value || 0));
}

function formatDate(value: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toISOString().slice(0, 10);
}

/** Middle ellipsis; same shape as admin payouts `truncateMiddle`. */
function truncateMiddle(value: string, prefix: number, suffix: number): string {
  if (value.length <= prefix + suffix + 3) return value;
  return `${value.slice(0, prefix)}...${value.slice(-suffix)}`;
}

async function copyTextToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      document.body.removeChild(ta);
      return ok;
    } catch {
      return false;
    }
  }
}

function StudioPayoutTxIdCell({
  txId,
  explorerUrl,
}: {
  txId: string;
  explorerUrl: string | null;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [preSuf, setPreSuf] = useState<{ prefix: number; suffix: number }>({
    prefix: 6,
    suffix: 4,
  });

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;

    const update = (): void => {
      const w = el.getBoundingClientRect().width;
      if (w < 88) setPreSuf({ prefix: 4, suffix: 3 });
      else if (w < 128) setPreSuf({ prefix: 5, suffix: 3 });
      else if (w < 180) setPreSuf({ prefix: 6, suffix: 4 });
      else setPreSuf({ prefix: 8, suffix: 6 });
    };

    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const display = truncateMiddle(txId, preSuf.prefix, preSuf.suffix);
  const linkClass =
    "min-w-0 flex-1 overflow-hidden text-ellipsis whitespace-nowrap font-mono text-[0.8125rem] text-neutral-900 underline underline-offset-2 hover:text-neutral-700 dark:text-neutral-100 dark:hover:text-neutral-300";

  return (
    <div
      ref={wrapRef}
      className="flex min-w-0 max-w-full items-center gap-1"
    >
      {explorerUrl ? (
        <a
          href={explorerUrl}
          target="_blank"
          rel="noreferrer"
          title={txId}
          onClick={() => {
            void copyTextToClipboard(txId);
          }}
          className={linkClass}
        >
          {display}
        </a>
      ) : (
        <span title={txId} className={`${linkClass} cursor-default no-underline`}>
          {display}
        </span>
      )}
      <button
        type="button"
        title={`Copy: ${txId}`}
        aria-label="Copy transaction ID"
        className="inline-flex shrink-0 rounded p-0.5 text-neutral-600 hover:bg-neutral-100 hover:text-neutral-900 dark:text-neutral-400 dark:hover:bg-neutral-800 dark:hover:text-neutral-100"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          void copyTextToClipboard(txId);
        }}
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 20 20"
          fill="currentColor"
          className="h-3.5 w-3.5"
          aria-hidden
        >
          <path d="M7 3.5A1.5 1.5 0 0 1 8.5 2h6A1.5 1.5 0 0 1 16 3.5v10a1.5 1.5 0 0 1-1.5 1.5h-1v-9A2.5 2.5 0 0 0 11 3.5H7Zm-2.5 3A2.5 2.5 0 0 0 2 9v6.5A2.5 2.5 0 0 0 4.5 18h6a2.5 2.5 0 0 0 2.5-2.5V9A2.5 2.5 0 0 0 10.5 6.5h-6Z" />
        </svg>
      </button>
    </div>
  );
}

export default function StudioPayoutsPage() {
  const { authReady, isAuthenticated } = useAuth();
  const [state, setState] = useState<PayoutState>({ status: "idle" });
  const [selectedMethod, setSelectedMethod] = useState<"crypto" | "bank" | "none">("none");
  const [walletAddress, setWalletAddress] = useState<string>("");
  const [saveNotice, setSaveNotice] = useState<{ type: "success" | "error"; message: string } | null>(
    null,
  );
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (!authReady) return;
    if (!isAuthenticated) {
      setState({ status: "idle" });
      return;
    }

    let cancelled = false;
    setState({ status: "loading" });
    setSaveNotice(null);

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

        const payouts = await fetchStudioArtistPayouts(artistId);
        if (!cancelled) {
          setSelectedMethod(payouts.payout_method.selected);
          setWalletAddress(payouts.payout_method.wallet_address ?? "");
          setState({ status: "ready", artistId, payouts });
        }
      } catch (err) {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : "Failed to load payouts";
          setState({ status: "error", message });
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [authReady, isAuthenticated]);

  if (state.status === "loading" || state.status === "idle") {
    return <p className="text-sm text-neutral-500 dark:text-neutral-400">Loading payouts...</p>;
  }

  if (state.status === "error") {
    return (
      <p className="text-sm text-red-600 dark:text-red-400" role="alert">
        {state.message}
      </p>
    );
  }

  if (state.status === "no_artist") {
    return (
      <p className="text-sm text-neutral-500 dark:text-neutral-400">
        No artist context available for this account.
      </p>
    );
  }

  const { payouts, artistId } = state as Extract<
    PayoutState,
    { status: "ready" }
  >;
  const summary = payouts.summary;
  const method = payouts.payout_method;
  const walletEnabled = selectedMethod === "crypto";

  async function handleSave(): Promise<void> {
    if (isSaving) return;
    setSaveNotice(null);

    if (selectedMethod === "crypto" && !walletAddress.trim()) {
      setSaveNotice({
        type: "error",
        message: "Wallet address is required when payout method is crypto.",
      });
      return;
    }

    if (selectedMethod === "bank" && !method.bank_configured) {
      setSaveNotice({
        type: "error",
        message:
          "Bank details are not editable in Studio yet. Configure bank payout through the legacy admin flow.",
      });
      return;
    }

    setIsSaving(true);
    try {
      await postStudioArtistPayoutMethod(artistId, {
        payout_method: selectedMethod,
        payout_wallet_address: selectedMethod === "crypto" ? walletAddress.trim() : "",
        // Studio does not expose bank detail content by design.
        payout_bank_info: "",
      });
      const refreshed = await fetchStudioArtistPayouts(artistId);
      setSelectedMethod(refreshed.payout_method.selected);
      setWalletAddress(refreshed.payout_method.wallet_address ?? "");
      setState({ status: "ready", artistId, payouts: refreshed });
      setSaveNotice({
        type: "success",
        message: "Payout method saved.",
      });
    } catch (err) {
      setSaveNotice({
        type: "error",
        message: err instanceof Error ? err.message : "Failed to save payout method.",
      });
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <section className="mx-auto max-w-4xl space-y-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Studio Payouts</h1>
      </header>

      <section className="rounded-lg border border-neutral-200 bg-white p-5 dark:border-neutral-800 dark:bg-neutral-950">
        <h2 className="mb-4 text-lg font-medium">Payout method</h2>
        <div className="space-y-3">
          <label className="flex items-center gap-2 text-sm text-neutral-700 dark:text-neutral-300">
            <input
              type="radio"
              name="payout_method"
              value="crypto"
              checked={selectedMethod === "crypto"}
              onChange={() => setSelectedMethod("crypto")}
            />
            Crypto (Algorand)
          </label>
          <label className="flex items-center gap-2 text-sm text-neutral-700 dark:text-neutral-300">
            <input
              type="radio"
              name="payout_method"
              value="bank"
              checked={selectedMethod === "bank"}
              onChange={() => setSelectedMethod("bank")}
            />
            Bank transfer
          </label>
          {method.selected === "none" ? (
            <p className="text-xs text-amber-700 dark:text-amber-300">No payout method configured</p>
          ) : null}
          <div className="space-y-1">
            <label
              htmlFor="studio_wallet_address"
              className="block text-sm font-medium text-neutral-900 dark:text-neutral-100"
            >
              Wallet address
            </label>
            <input
              id="studio_wallet_address"
              type="text"
              value={walletAddress}
              onChange={(e) => setWalletAddress(e.target.value)}
              disabled={!walletEnabled || isSaving}
              placeholder={walletEnabled ? "Enter Algorand wallet address" : "Disabled for bank payout"}
              className="mt-1 block w-full max-w-2xl rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 disabled:cursor-not-allowed disabled:bg-neutral-100 disabled:text-neutral-500 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100 dark:disabled:bg-neutral-800 dark:disabled:text-neutral-500"
            />
          </div>
          <p className="text-sm text-neutral-600 dark:text-neutral-400">
            <span className="font-medium text-neutral-900 dark:text-neutral-100">Bank configured:</span>{" "}
            {method.bank_configured ? "Yes" : "No"}
          </p>
          <button
            type="button"
            disabled={isSaving}
            className="mt-2 rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-neutral-300"
            onClick={() => {
              void handleSave();
            }}
          >
            {isSaving ? "Saving..." : "Save payout method"}
          </button>
          {saveNotice ? (
            <p
              className={`text-xs ${
                saveNotice.type === "success"
                  ? "text-emerald-700 dark:text-emerald-300"
                  : "text-red-600 dark:text-red-400"
              }`}
              role={saveNotice.type === "error" ? "alert" : undefined}
            >
              {saveNotice.message}
            </p>
          ) : null}
        </div>
      </section>

      <section className="rounded-lg border border-neutral-200 bg-white p-5 dark:border-neutral-800 dark:bg-neutral-950">
        <h2 className="mb-4 text-lg font-medium">Summary</h2>
        <div className="space-y-1 text-sm text-neutral-600 dark:text-neutral-400">
          <p>
            <span className="font-medium text-neutral-900 dark:text-neutral-100">Paid out to you:</span>{" "}
            {formatEur(summary.paid_eur)}
          </p>
          <p className="pb-2 text-xs text-neutral-500 dark:text-neutral-500">
            Amount already transferred to you.
          </p>
          <p>
            <span className="font-medium text-neutral-900 dark:text-neutral-100">
              Generated, pending payout:
            </span>{" "}
            {formatEur(summary.accrued_eur)}
          </p>
          <p className="pb-2 text-xs text-neutral-500 dark:text-neutral-500">
            Earnings generated from your streams that will be included in the next payout.
          </p>
          {Number(summary.pending_eur) > 0 ? (
            <>
              <p>
                <span className="font-medium text-neutral-900 dark:text-neutral-100">
                  Currently being processed:
                </span>{" "}
                {formatEur(summary.pending_eur)}
              </p>
              <p className="pb-2 text-xs text-neutral-500 dark:text-neutral-500">
                Payout currently being processed. This may take some time.
              </p>
            </>
          ) : null}
          <p>
            <span className="font-medium text-neutral-900 dark:text-neutral-100">
              Number of payments:
            </span>{" "}
            {summary.batch_count}
          </p>
          <p className="pt-2">
            <span className="font-medium text-neutral-900 dark:text-neutral-100">Last payment date:</span>{" "}
            {formatDate(summary.last_batch_date)}
          </p>
        </div>
      </section>

      <section className="rounded-lg border border-neutral-200 bg-white p-5 dark:border-neutral-800 dark:bg-neutral-950">
        <h2 className="mb-4 text-lg font-medium">Payout history</h2>
        {payouts.history.length === 0 ? (
          <p className="text-sm text-neutral-500 dark:text-neutral-400">No payouts yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-neutral-200 text-left dark:border-neutral-800">
                  <th className="px-2 py-2 font-medium">Date</th>
                  <th className="px-2 py-2 font-medium">Amount</th>
                  <th className="px-2 py-2 font-medium">Status</th>
                  <th className="max-w-[min(42vw,11rem)] min-w-0 px-2 py-2 font-medium sm:max-w-[14rem]">
                    Tx ID
                  </th>
                  <th className="px-2 py-2 font-medium">Users</th>
                </tr>
              </thead>
              <tbody>
                {payouts.history.map((row: StudioPayoutHistoryRow) => (
                  <tr key={row.batch_id} className="border-b border-neutral-100 dark:border-neutral-900">
                    <td className="px-2 py-2">{formatDate(row.date || null)}</td>
                    <td className="px-2 py-2">{formatEur(row.amount_eur)}</td>
                    <td className="px-2 py-2 capitalize">{row.status}</td>
                    <td className="max-w-[min(42vw,11rem)] min-w-0 px-2 py-2 sm:max-w-[14rem]">
                      {row.tx_id ? (
                        <StudioPayoutTxIdCell
                          txId={row.tx_id}
                          explorerUrl={
                            row.explorer_url != null && String(row.explorer_url).trim()
                              ? String(row.explorer_url).trim()
                              : null
                          }
                        />
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="px-2 py-2">{row.users || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </section>
  );
}
