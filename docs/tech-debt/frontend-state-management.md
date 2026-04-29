Type: TECH_DEBT
Status: PARTIALLY_IMPLEMENTED
Linked State: /docs/state/frontend.md
Last Verified: 2026-04-29

## Phase 2 — State management refactor (planned)

Context:
We fixed `react-hooks/set-state-in-effect` issues using minimal changes (moving initial state out of effects).

Current limitation:
- multiple pages still use ad-hoc loading/data patterns
- state transitions are implicit and duplicated

Future improvement:
- migrate to a consistent pattern (e.g. useReducer or data-fetching hooks)
- standardize states: idle / loading / success / error
- centralize async logic

Status:
Deferred (post-MVP stabilization)

## Phase 2 — State Management Improvements

### Current state (after fix)

- Hooks now follow a safe minimal pattern across lint-fixed files:
  - no synchronous `setState` at effect start
  - effects handle async work and async-driven state updates
  - cancellation guards are used where async work can outlive component lifecycle
- Existing behavior and flow logic were preserved while removing lint violations.

### Limitations

- Complex pages still spread related state across many `useState` calls.
- Related transitions are often implicit rather than modeled explicitly.
- Async status handling is not yet unified in one reusable pattern.

### Future direction

- Introduce `useReducer` for complex, multi-step flows (e.g. upload wizard).
- Consider lightweight global state (e.g. Zustand) only when cross-page coordination justifies it.
- Unify async state shape and transitions (`loading` / `error` / `success`) across page-level fetchers.

### Status

Deferred (post-MVP stabilization)

## Related State
- /docs/state/frontend.md

## Alignment

- Vision: Human-centered streaming, user-centric model
- State: /docs/state/frontend.md
