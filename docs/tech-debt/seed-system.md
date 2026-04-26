# Seed System Tech Debt

## Current Coverage

The seed system now generates realistic users, one artist per user, multi-release catalogs, song media, listening activity, and payout snapshots/lines in one orchestrated flow.

## Missing Product Entities

- Playlists: no user or editorial playlists are seeded yet.
- Curators: no curator identities, follows, or recommendation graph.
- Editorial posts: no release stories, interviews, or campaign content.
- Labels: no label hierarchy, roster membership, or label payout models.

## Slug Coverage Gaps

- Slug generation is validated for artists/releases/songs, but redirects/history behavior is not seeded with rename scenarios.
- No stress run currently tests large-batch slug collisions beyond one intentional duplicate song title.
- Label/playlist/editorial entities have no slug lifecycle yet.

## Future Realism Improvements

- Regionalized metadata and localized release windows.
- Richer release configurations (pre-save, schedules, staggered publishing).
- Listener cohorts with different retention behavior and skip rates.
- Seasonality campaigns and discovery boosts affecting long-tail movement.
- Refunds/chargebacks in balance pools to test payout negative adjustments.

## Seed vs Real Blockchain Behavior

- Seed runs use real payout and settlement flows; no mocking layer is used for blockchain calls.
- Network and funding failures are expected in dev environments and are treated as non-blocking.
- Seed orchestration keeps deterministic data creation (users, artists, catalog, listening, payout_lines) even when settlement attempts fail.
- Settlement outcomes are logged and recorded as `failed` or `pending/submitted` statuses rather than crashing the seed run.
