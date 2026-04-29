Type: TECH_DEBT
Status: PARTIALLY_IMPLEMENTED
Linked State: /docs/state/discovery.md
Last Verified: 2026-04-29

# Discovery Tech Debt

This file tracks current discovery limitations that are actionable as tech debt.

Future architecture blueprints were moved to:
- `docs/future/discovery-advanced-system.md`

## Active Tech Debt

- Discovery ranking still relies on limited catalog metadata and aggregate listening signals.
- Curator lane remains an allowlist/editorial simulation, not a full curator identity/economy system.
- Cultural relationship modeling (scene/graph context) is not implemented.
- No real-time session-level re-ranking or event-loop feedback in discovery responses.
- Personalization depth is limited; advanced quality/exposure governance is not implemented.

## Why this split exists

- `docs/tech-debt/` stays focused on current constraints and near-term prioritization.
- `docs/future/` preserves long-term models without presenting them as current implementation commitments.

## Related State
- /docs/state/discovery.md

## Alignment

- Vision: Human-centered streaming, user-centric model
- State: /docs/state/discovery.md
