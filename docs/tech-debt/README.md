Type: TECH_DEBT
Status: PARTIALLY_IMPLEMENTED
Linked State: /docs/state/README.md
Last Verified: 2026-04-29

# Tech debt index

## What this is

This folder tracks **intentional deferrals** and **known gaps** from building the Human Music Platform MVP. Items here are not bugs in the sense of “broken by accident”—they are tradeoffs, missing features, or policies left open so shipping could stay focused.

**This directory (`docs/tech-debt/`) is the single source of truth** for tech debt on this project.

## Why decisions were postponed

- **Velocity:** Hybrid listening (sessions, checkpoints, finalize) and the global player shipped as an MVP ingestion path before full recovery, policy alignment, and distributed ops.
- **Product ambiguity:** Some behaviors (e.g. whether an idle-expired session may still be finalized economically) need explicit product + legal alignment before encoding in the API.
- **Cost of correctness:** Session recovery, sendBeacon-style unload, buffering-aware time, and distributed rate limits require non-trivial design and testing.

## How to use this system

1. Start with **priority** (below) when planning sprints or pre-release hardening.
2. Open the **category file** for full context: description, current behavior, proposed direction, and when to address.
3. When an item is done, either **remove it** or add a short “Resolved” subsection with link to PR/issue—keep the index honest.

## Categories (files)

| File | Focus |
|------|--------|
| [ingestion.md](./ingestion.md) | Listening pipeline integrity: sessions, checkpoints, finalize, recovery, server policy |
| [player.md](./player.md) | Global audio client: timing accuracy, unload, background behavior, persistence |
| [player_ux.md](./player_ux.md) | **LOW (Frontend / UX):** Advanced player polish — queue UI, waveform progress, “Up Next” preview |
| [backend.md](./backend.md) | API, scaling, rate limits, session lifecycle, search (summary), schema evolution (credits, identifiers) |
| [economics.md](./economics.md) | **HIGH / CRITICAL:** Payout wallet policy, rights entities, policy versioning vs `validate_listen`, settlement audit exports |
| [infra.md](./infra.md) | **HIGH:** Observability, Postgres migration bundle, queues/workers, secrets, E2E tests, dev bootstrap polish |
| [product.md](./product.md) | **MEDIUM / LOW:** Monetization, onboarding, dashboard depth, public API, geo analytics, fan score |
| [storage_and_media.md](./storage_and_media.md) | **MEDIUM:** Local `/uploads`, readable filenames, public paths → object storage, CDN, signed URLs, UUID keys, transcoding |
| [ux.md](./ux.md) | Surfaces around player, uploads, catalog, errors |
| [search_scalability.md](./search_scalability.md) | **Deep dive:** artist search implementation, limits, options (Postgres/SQLite/external), upgrade triggers |
| [auth-and-wallet.md](./auth-and-wallet.md) | **HIGH:** Current auth/wallet migration blockers and security debt (future architecture moved to `docs/future/auth-and-wallet-architecture.md`) |
| [auth-system.md](./auth-system.md) | **Auth umbrella:** refresh families / reuse / logout-all, CSRF, email flows, DB email NOT NULL, legacy header removal, frontend session, JWT risks, production checklist |
| [discovery-advanced-system.md](./discovery-advanced-system.md) | **Discovery debt:** current V1 limitations (future ranking blueprint moved to `docs/future/discovery-advanced-system.md`) |
| [roles.md](./roles.md) | **Cross-domain onboarding/roles debt:** role duplication, route guard scope, onboarding-state constraints, resolver/redirect risks |
| [startup-schema-seed-separation.md](./startup-schema-seed-separation.md) | **HISTORICAL / MOSTLY RESOLVED:** documents the prior startup/schema/seed coupling and the adopted Alembic-first + explicit-seed model |

## Priority levels

| Level | Meaning | Typical action |
|-------|---------|----------------|
| **CRITICAL** | Can affect **economic data, payouts, or auditability** of listens | Address before trusting money on the line; may block “production payouts” |
| **HIGH** | **Robustness or UX** failures under real users (data loss, confusion, support load) | Next major milestone after MVP hardening |
| **MEDIUM** | Clear improvements; workarounds exist | Backlog, prioritize by impact |
| **LOW** | Polish, optimization, nice-to-have | As time allows |

## Suggested sequencing (non-binding)

1. **CRITICAL ingestion + backend policy** alignment (what counts as a listen, refresh/orphans).
2. **CRITICAL economics** ([economics.md](./economics.md)) — align live validation with versioned policies before widening payout experiments.
3. **HIGH player** unload and engaged-time policy where antifraud cares.
4. **HIGH/MEDIUM backend** rate limiting and session lifecycle for multi-instance deploys; **HIGH infra** ([infra.md](./infra.md)) observability + E2E gates in parallel once deploys multiply.
5. **Postgres + worker hardening** — pair [backend.md](./backend.md) ingestion locks with [infra.md](./infra.md) DB migration runbook.
6. **MEDIUM/LOW UX** once ingestion story is stable; extend upload metadata per [ux.md](./ux.md) when partners require splits/identifiers ([backend.md](./backend.md)).
7. **MEDIUM storage and media** ([storage_and_media.md](./storage_and_media.md)) before production scale or when private/unreleased playback policy is required (includes transcoding when egress/mobile matters).
8. **Product** ([product.md](./product.md)) — monetization, onboarding, dashboard, public API — after reliability baseline.
9. **LOW advanced player UX** ([player_ux.md](./player_ux.md)) — queue drawer, waveform, up-next preview — after streaming stability; optional before beta/public if UX is a launch gate.

## Future layer

Forward-looking system designs now live in `docs/future/`:

- `docs/future/discovery-advanced-system.md`
- `docs/future/auth-and-wallet-architecture.md`

---

*Last curated as part of structured tech-debt documentation (MVP → production evolution). Reconciliation pass: manual backlog vs codebase, 2026-04-12 — added economics / infra / product, merged items into existing category files without removing prior entries.*

## Related State
- /docs/state/README.md

## Alignment

- Vision: Human-centered streaming, user-centric model
- State: /docs/state/README.md
