/**
 * Conceptual layout for the artist dashboard (maps to GET /artist-dashboard data).
 * Three isolated sections — no mixing analytics fields with payout fields in the same block.
 *
 * Expected API shape (subset):
 * - estimated_total
 * - paid, pending
 * - spotify_total, difference (benchmark vs payout total)
 */

export type ArtistDashboardData = {
  artist_id: number;
  estimated_total: number;
  paid: number;
  pending: number;
  spotify_total: number | null;
  difference: number | null;
  last_paid_payouts?: Array<{ date: string; amount: number }>;
  next_payout_date?: string;
};

/** Section 1 — analytics only */
export function EstimatedEarningsSection({ data }: { data: ArtistDashboardData }) {
  return (
    <section aria-labelledby="est-heading">
      <h2 id="est-heading">🎧 Estimated Earnings (not yet paid)</h2>
      <p>
        This amount updates continuously based on listening activity and may
        increase or decrease until the next payout.
      </p>
      <p>
        <strong>Estimated amount:</strong> {data.estimated_total} €
      </p>
      <p>
        Analytics tab contains charts, per-song insights, and detailed breakdowns.
      </p>
    </section>
  );
}

/** Section 2 — ledger only */
export function PayoutsSection({ data }: { data: ArtistDashboardData }) {
  return (
    <section aria-labelledby="pay-heading">
      <h2 id="pay-heading">💸 Payouts</h2>
      <p>Processed earnings that have been paid or are pending.</p>
      <p>
        <strong>Total paid to date:</strong> {data.paid} €
      </p>
      <h3>Last payouts</h3>
      <ul>
        {(data.last_paid_payouts ?? []).slice(0, 3).map((row) => (
          <li key={`${row.date}-${row.amount}`}>
            {row.date} — {row.amount} €
          </li>
        ))}
      </ul>
      <p>
        <a href={`/artist-payouts/${data.artist_id}`}>View all payouts →</a>
      </p>
      <p>
        <strong>Next payout:</strong> {data.next_payout_date ?? "—"}
      </p>
      {data.estimated_total <= 0 ? (
        <p>
          This payout will include your first earnings once you start generating
          revenue.
        </p>
      ) : null}
      {data.pending > 0 ? (
        <p>
          <strong>Pending payout:</strong> {data.pending} €
        </p>
      ) : null}
    </section>
  );
}

/** Section 3 — benchmark vs payout total */
export function BenchmarkSection({ data }: { data: ArtistDashboardData }) {
  const isNegative = (data.difference ?? 0) < 0;
  return (
    <section aria-labelledby="bench-heading">
      <h2 id="bench-heading">📊 Global Model Comparison</h2>
      {isNegative ? (
        <p>
          Your audience is supporting you directly.
          <br />
          You are earning what is fair while contributing to a more balanced and
          sustainable music ecosystem.
          <br />
          <br />
          Thank you for inspiring the world.
        </p>
      ) : null}
      {!isNegative ? (
        <>
          <p>Global model estimate: {data.spotify_total ?? "—"} €</p>
          <p>
            {(data.difference ?? 0) > 0 ? "+" : ""}
            {data.difference ?? "—"} € vs global model
          </p>
          <p>
            Comparison based on payout earnings vs global pool model (ex:
            Spotify, Apple Music, Amazon, YouTube, etc)
          </p>
        </>
      ) : null}
      {isNegative ? (
        <details>
          <summary>See how this compares to traditional streaming platforms</summary>
          <p>Global model estimate: {data.spotify_total ?? "—"} €</p>
          <p>{data.difference ?? "—"} € vs global model</p>
          <p>
            Comparison based on payout earnings vs global pool model (ex:
            Spotify, Apple Music, Amazon, YouTube, etc)
          </p>
        </details>
      ) : null}
    </section>
  );
}

export function ArtistDashboardPage({ data }: { data: ArtistDashboardData }) {
  return (
    <main>
      <nav aria-label="Artist dashboard navigation">
        <a href={`/artist-dashboard/${data.artist_id}`}>
          <strong>Overview</strong>
        </a>{" "}
        | <a href={`/artist-analytics/${data.artist_id}`}>Analytics</a> |{" "}
        <a href={`/artist-payouts/${data.artist_id}`}>Payouts</a> |{" "}
        <a href={`/artist-profile/${data.artist_id}`}>Profile</a>
      </nav>
      <EstimatedEarningsSection data={data} />
      <PayoutsSection data={data} />
      <BenchmarkSection data={data} />
    </main>
  );
}
