Type: TECH_DEBT
Status: PARTIALLY_IMPLEMENTED
Linked State: /docs/state/economics.md
Last Verified: 2026-04-29

## Participant Share Mapping

- `participants` payloads intentionally omit royalty share values.
- Frontend should map share by joining `participants.artist_id` with `splits.artist_id`.
- This keeps permission/approval state (`participants`) separate from economics (`splits`).
- Future improvement: optionally embed share directly in participant payloads for simpler UI rendering.

## Participant share normalization (future)

- Currently, `participants` do not map 1:1 to split rows; frontend joins split values manually.
- Future improvement is to emit normalized participant-share rows from backend, for example:

```ts
{
  id: "artist_1_composer",
  artist_id: 1,
  role: "composer",
  share: 10
}
```

- This would remove frontend join logic and support multi-role participation more cleanly.
- Status: `Deferred — post-MVP (requires redesign of approval model)`.

## Related State
- /docs/state/economics.md

## Alignment

- Vision: Human-centered streaming, user-centric model
- State: /docs/state/economics.md
