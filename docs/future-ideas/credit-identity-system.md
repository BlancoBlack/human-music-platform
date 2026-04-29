Type: FUTURE_IDEA
Status: NOT_IMPLEMENTED
Linked State: /docs/state/README.md
Last Verified: 2026-04-29

# Credit-Identity System

**Status:** Concept exploration (future-facing)
**Role Lens:** Senior Product Architect + Systems Designer

---

## Goal

Document a future-facing idea: evolving credits from plain text into a linked identity system for professionals (engineers, producers, and similar contributors).

This is a conceptual product exploration document, not an implementation plan.

---

## 1. Problem Today

Current credits are mostly plain text.

- Credits are **plain text**
- There is no identity linkage
- There is no reliable way to:
  - Explore a contributor's wider body of work
  - Verify authorship with confidence
  - Build contributor reputation over time

Result:

- Lost value in metadata
- No meaningful network effects around contributors
- No discovery experience based on people behind the work

---

## 2. Vision

Transform credits into a **linked identity graph**.

Instead of:

```text
Mix Engineer: John Doe
```

We have:

```text
Mix Engineer: John Doe (linked profile)
```

Where:

- John Doe is a **platform user**
- Credits become **navigable + verifiable**

---

## 3. Core Concept

Credits can optionally include a user link:

```ts
{
  name: string,
  role: string,
  user_id?: number
}
```

- `name` -> always present (backward compatible)
- `user_id` -> optional link to a platform user

This keeps the current system intact while enabling linked identity where available.

---

## 4. User Types Involved

### Professional (future role)

Introduce a future role type for contributors whose primary value is credited work, not artist uploads.

A Professional:

- Cannot upload music
- Can:
  - Be credited on tracks/releases
  - Build a public profile
  - Accumulate visible work history

Examples:

- Mixing engineers
- Mastering engineers
- Producers
- Sound designers

---

## 5. Claim System (Critical)

### Problem

Many credits will initially exist as plain text with no linked account.

### Solution

Allow users to **claim credits**.

### Flow

1. User finds a track where they are credited
2. User clicks: **"This is me"**
3. System creates a **claim request**

### Statuses

- `pending`
- `accepted` (by artist)
- `rejected`

This is the bridge from unlinked text credits to trusted identity links.

---

## 6. Artist Control

The artist remains the **source of truth**.

Artist approval is required for:

- Credit claims
- Identity linking

This prevents:

- Fake claims
- Credit hijacking

---

## 7. Profile System

Each professional profile can include:

- List of credited works
- Role breakdown (e.g., mix vs mastering)
- Genres worked in
- Potentially:
  - Playlists (curation layer)

This turns credits into a living portfolio rather than static metadata.

---

## 8. Discovery Implications

A linked credit graph enables discovery paths such as:

- "Tracks mixed by X"
- "Top mastering engineers in genre Y"
- "People behind the sound"

Credits become:

- Discovery signal
- Reputation layer
- Trust layer

---

## 9. Future Extensions

Possible future expansions:

- Verified professionals (badge)
- Reputation scoring
- Hiring / collaboration layer
- Credit-based recommendation systems

These are optional future opportunities, not first-phase requirements.

---

## 10. Design Constraints

- Must remain **backward compatible**
- Credits must still work without user linkage
- No forced identity system
- Initial implementation should stay minimal

---

## 11. Implementation Strategy (High-Level)

### Phase 1

- Add optional `user_id` to credits

### Phase 2

- Display linked credits in product surfaces

### Phase 3

- Introduce claim system

### Phase 4

- Introduce role system (Professional)

---

## Success Criteria

- Clear articulation of the idea
- No implementation detail mixed with speculative product direction
- Easy to revisit during future roadmap planning

---

## Strategic Note

This is a **strategic feature**, not a quick iteration.

It should be implemented only when:

- Core product is stable
- Discovery system is mature
- User graph begins to matter materially

---

## Related State
- /docs/state/README.md

## Alignment

- Vision: Human-centered streaming, user-centric model
- State: /docs/state/README.md
