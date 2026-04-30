# Admin surface — tech debt

## MULTI-ADMIN COLLABORATION (FUTURE)

- **Real-time visibility** of which admins are actively running batch operations (settle / retry), beyond inferring from `payout_batches.status = processing`.
- **Ownership** of batch processing: explicit “claimed by” semantics, optional forced handoff, and audit of who held the lock when.
- **Conflict resolution UI** when two admins attempt the same batch: richer than HTTP 409 + message (e.g. link to activity log, suggested wait/retry).
- **Presence system** (optional): lightweight “admin X is on payouts page” without committing to full collaborative editing.

Current mitigation: DB-level lock + HTTP 409 + client messaging and polling backoff (`docs/state/frontend.md` **UX HARDENING**).
