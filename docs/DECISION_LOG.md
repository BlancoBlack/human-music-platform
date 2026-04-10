# DECISION_LOG.md

# 1. PURPOSE

This document records **important product, technical, and economic decisions**.

Its goals:

- prevent repeating discussions
- preserve reasoning
- avoid silent product drift
- maintain alignment over time

Each decision must include:

- context
- decision
- reasoning
- alternatives considered
- consequences

---

# 2. DECISION TEMPLATE

## [DATE] — [TITLE]

### Context
What problem or situation triggered this decision?

### Decision
What was decided?

### Reasoning
Why this decision was made.

### Alternatives Considered
Other options that were evaluated.

### Consequences
Expected impact (positive and negative).

### Status
- active
- deprecated
- under review

---

# 3. CORE DECISIONS

## Blockchain is Invisible

### Context
Blockchain introduces UX friction.

### Decision
Hide all blockchain complexity from users.

### Reasoning
UX simplicity > technological purity.

### Alternatives Considered
- exposed wallets
- token-based UX

### Consequences
+ mainstream adoption
- less "crypto-native" appeal

### Status
active

---

## User-Centric Payment Model

### Context
Pro-rata models are unfair to artists.

### Decision
Each user pays only for what they listen to.

### Reasoning
Aligns value with consumption.

### Alternatives Considered
- pro-rata model

### Consequences
+ fairer payouts
+ strong differentiation

### Status
active

---

## Hybrid Architecture

### Context
Full on-chain systems are slow and expensive.

### Decision
Use blockchain only for settlement.

### Reasoning
Performance + cost efficiency.

### Alternatives Considered
- full on-chain streaming

### Consequences
+ scalability
+ lower costs

### Status
active

---

## Human-Centered Music Policy

### Context
AI-generated spam is increasing.

### Decision
Allow AI as tool, ban mass-generated content.

### Reasoning
Protect cultural value.

### Alternatives Considered
- full AI ban
- full AI openness

### Consequences
+ strong positioning
+ defensible moderation

### Status
active

---

## Curator Economy

### Context
Discovery is broken in algorithm-only systems.

### Decision
Introduce curator rewards (1–2%).

### Reasoning
Reintroduce human taste into discovery.

### Alternatives Considered
- algorithm-only
- editorial-only

### Consequences
+ richer discovery
+ cultural layer

### Status
active

---

# 4. RULES

- Never delete decisions → mark as deprecated
- Always log major architectural changes
- Always log economic model changes
- Always log UX paradigm changes

---

# END OF FILE