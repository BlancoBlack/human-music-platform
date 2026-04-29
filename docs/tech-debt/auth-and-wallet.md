Type: TECH_DEBT
Status: PARTIALLY_IMPLEMENTED
Linked State: /docs/state/auth.md
Last Verified: 2026-04-29

# Auth + Wallet Tech Debt

This file tracks current auth/wallet limitations and migration blockers.

Future architecture options and long-horizon design material were moved to:
- `docs/future/auth-and-wallet-architecture.md`

## Active Tech Debt

- Legacy auth fallback (`X-User-Id`) still exists in code as opt-in compatibility and should be fully retired once no clients depend on it.
- Refresh/session hardening is incomplete (family rotation/reuse-detection and robust device/session inventory remain partially deferred).
- Wallet custody design is intentionally deferred, but payout evolution depends on a clear canonical wallet model and settlement snapshot invariants.
- Wallet/signing security controls (KMS/MPC choice, isolated signer, immutable audit pipeline) are not active production capabilities yet.

## Migration Constraints (current)

- Do not introduce custodial private-key storage in application DB as a shortcut.
- Preserve a single source of truth for payout destination semantics at settlement boundaries.
- Complete auth hardening before expanding high-risk payout mutation surfaces.

## Related State
- /docs/state/auth.md

## Alignment

- Vision: Human-centered streaming, user-centric model
- State: /docs/state/auth.md
