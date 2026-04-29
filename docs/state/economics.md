# Economics — current implementation

## AUDIT SNAPSHOT (2026-04-29) — Payout Truth, Preview Models, Ledger

## CURRENTLY IMPLEMENTED

- Payout truth in artist/studio dashboards is ledger-based (`payout_lines` + `payout_batches` + `payout_settlements`).
- "Paid" means settlement-confirmed on-chain (`execution_status='confirmed'`).
- "Accrued" means finalized/posted ledger value not yet confirmed on-chain.
- "Pending" means batches still calculating.
- Snapshot-based V2 payout flow exists end-to-end:
  - snapshot inputs,
  - deterministic line generation,
  - settlement worker execution and status progression.
- Preview/comparison model still exists and is separate:
  - `GET /payout/{user_id}` user-centric preview,
  - `GET /compare/{user_id}` user-centric vs global comparison.

## PARTIALLY IMPLEMENTED

- Product semantics are partially unified:
  - creator dashboard earnings are ledger-backed,
  - user payout/compare endpoints are still preview-oriented and can be interpreted as "earnings" by non-technical readers.
- Some "estimated" analytics helpers are implemented but not consistently surfaced in current studio UI contracts.

## NOT IMPLEMENTED

- No evidence of a fully unified payout API contract that eliminates preview-vs-ledger ambiguity across all UI surfaces.
- No dedicated React `/studio/payouts` production feature using full ledger history yet (page is placeholder on frontend).

## KNOWN ISSUES

- Currency semantics are inconsistent across paths (preview metadata vs batch defaults).
- Estimated earnings helpers can be computationally heavy at scale.

## ⚠️ SYSTEM INCONSISTENCIES

- REAL vs ESTIMATED answer:
  - Studio/artist dashboard payout totals are **REAL ledger-based values** with explicit settled/accrued/pending buckets.
  - User-centric payout/compare endpoints are **ESTIMATED/PREVIEW model outputs**, not settlement-truth payouts.
- Mixed economics narratives in the product can mislead if UI labels do not clearly distinguish "settled earnings" from "model preview."

## CURRENTLY IMPLEMENTED

### User-centric preview (live aggregates, not ledger)

- **`calculate_user_distribution(user_id)`** (`payout_service.py`): reads `UserBalance` + `ListeningAggregate` for user; builds artist pool `monthly_amount * ARTIST_SHARE`; allocates by **weighted** listening mass when `total_weighted > epsilon`, else raw duration fallback, else treasury sink song/artist (`ensure_treasury_entities` / `get_treasury_song`). Returns list entries with `song_id`, shares, `payout`, `cents`, etc. (see function return shape in code).
- **`GET /payout/{user_id}`**: JSON preview + `expand_song_distribution_to_artists` for per-artist cents; conservation check songs vs artists. Access restricted by `require_self_or_admin(user_id)`.
- **Splits**: `SongArtistSplit` + helpers (`song_split_distribution`, `song_artist_split_service`, `set_splits_for_song`) used where expansion requires per-song multi-artist allocation.

### Global pool model (comparison / “Spotify-style” benchmark in code comments)

- **`calculate_global_distribution()`** (`pool_payout_service.py` — imported by routes): drives **`GET /pool-distribution`**.
- **`compare_models(user_id)`** (`comparison_service.py`): pairs user-centric lines with global pool shares; scales pool amounts to the **same user artist pool** base (`ARTIST_SHARE` of that user’s `monthly_amount`); **filters system songs** out of both sides; returns `comparison` list and `user_id`. Used by **`GET /compare/{user_id}`** and HTML `GET /dashboard/{user_id}`; both now require `require_self_or_admin(user_id)`.

### Artist dashboard numbers (ledger-centric)

- **`get_artist_dashboard(artist_id)`** (`artist_dashboard_service.py`): aggregates from **`payout_lines`** joined with **`payout_batches`** / **`payout_settlements`**:
  - **Total** — sum of all lines for artist.
  - **Paid** — lines where settlement `execution_status == 'confirmed'`.
  - **Accrued** — batches `finalized` or `posted` but settlement missing or not confirmed/failed.
  - **Failed** — settlement `execution_status == 'failed'`.
  - **Pending** — batches `status == 'calculating'`.
- **Spotify equivalent field**: `calculate_artist_spotify_equivalent(artist_id)` from `pool_payout_service` — exposed as `spotify_total` + `difference` vs ledger total.
- **HTML** `GET /artist-dashboard/{artist_id}` renders the above; does **not** call `get_artist_estimated_total`; access now requires `require_artist_owner(artist_id)`.

### “Estimated” analytics model (dynamic, not ledger)

- **`get_artist_estimated_total(artist_id)`** and **`get_artist_estimated_earnings_by_song(artist_id)`** (`analytics_service.py`): iterate **all** `UserBalance` rows, run `calculate_user_distribution` per user, split each song line to artists via `split_song_amount_to_artists`, sum share for the target artist; excludes system songs via cache helper. Documented as **analytics only**, same path as time-bucketed earnings helpers.
- **Mismatch vs secondary context / UI**: backend **dashboard payload does not include** `estimated_total`. Frontend file `ArtistDashboardSections.tsx` **expects** `estimated_total` but that component is **not imported elsewhere** in the frontend grep snapshot — so “estimated earnings on dashboard” is **partially** realized (library function exists; primary HTML dashboard omits it).

### Ledger V2 (snapshot → lines → batch → settlement)

- **Models**:
  - `PayoutBatch`: `status IN ('draft','calculating','finalized','posted')`, `snapshot_id` FK optional until bound, `calculation_version` default **`v2`**, period columns, `source_snapshot_hash`, etc.
  - `PayoutInputSnapshot` + `SnapshotUserPool` + `SnapshotListeningInput`: sealed snapshot inputs (`snapshot_service.build_snapshot`).
  - `PayoutLine`: per batch, song, artist, `amount_cents`, line typing/idempotency as implemented in engine.
  - `PayoutSettlement`: one row per `(batch_id, artist_id)`; `execution_status IN ('pending','submitted','confirmed','failed')`; `breakdown_json`, `breakdown_hash`, optional `destination_wallet`, `algorand_tx_id`, attempt fields.
- **`generate_payout_lines`** (`payout_v2_snapshot_engine.py`): integer allocation + split validation (basis points sum 10_000); invoked from scripts/seeding and admin-style workflows (see routes + seed scripts).
- **Settlement worker** (`settlement_worker.py`): Algorand **ASA USDC** transfer path (`USDC_ASSET_ID = 10458941` in code), uses `AlgorandClient` from `algorand_client_v2.py`; verifies pool conservation via `settlement_breakdown`; statuses **pending → submitted → confirmed** (and **failed**).
- **Admin routes**: `POST /admin/settle-batch/{batch_id}`, `POST /admin/retry-payout/{payout_id}`, `GET /admin/payouts`, HTML `admin/payouts-ui`.
- **Explorer URLs**: `routes.py` sets Lora Algokit explorer base from `NETWORK` env (`mainnet` vs default testnet).
- **USDC transfer note**: `settlement_worker` passes a JSON **note** on the ASA transfer: `{ "a": artist_id, "b": batch_id, "h": breakdown_hash }` (auditable linkage; not a substitute for full cross-system idempotency design).

### Global model on sealed snapshot (V2 comparison helper)

- **`compare_models_v2_snapshot` / `compare_models_v2`** (`global_model_v2_service.py`): recomputes user vs global allocation from **`snapshot_user_pools`** + **`snapshot_listening_inputs`** for a batch with sealed snapshot — used in tests/scripts (`test_distribution_vs_ledger_parity.py`), **not** the same as simple `GET /compare/{user_id}` which uses live aggregates.

## PARTIALLY IMPLEMENTED

- **Naming mismatch**: informal docs refer to **`generate_payouts`**; the implemented batch line generator is **`generate_payout_lines`** (no symbol named `generate_payouts` found in backend grep).
- **Algorand client**: `algorand_client_v2.py` hardcodes **testnet** algod URL in source; settlement asset id is constant — **mainnet readiness** for client URL/asset id is not fully parameterized in that file alone.
- **Estimated earnings “since last payout”**: `get_artist_estimated_total` reflects **current** user-centric model over all subscribers, **not** “delta since last batch period” unless callers compute a diff (**not** implemented as a single API field in reviewed routes).

## NOT IMPLEMENTED

- **Classic `Payout` ORM table / V1 row-per-payment model**: not in the `database.py` model import list; economics truth in UI is **`payout_lines`** + settlements.
- **End-to-end documented recovery** for “chain succeeded, DB update lost”: admin retry exists, but a **formal** idempotency playbook across all failure orders is **not** spelled out in code comments reviewed as a single spec.

## KNOWN ISSUES

- **Currency labels**: `GET /payout/{user_id}` meta uses **`EUR`** while batches default currency column is **`USD`** in `PayoutBatch` — potential **product/schema inconsistency** to reconcile operationally.
- **Estimated total cost**: `get_artist_estimated_total` scans **all** user balances and recomputes distributions — **O(users × distribution work)**; may be heavy at scale (no pagination/caching in function body).
- **Treasury / system songs**: multiple code paths explicitly exclude or sink system entities; misconfiguration could still skew previews if aggregates point at treasury incorrectly.
