Type: SYSTEM
Status: UNKNOWN
Linked State: /docs/state/README.md
Last Verified: 2026-04-29

# LLM_CONTEXT.md

# 1. PURPOSE OF THIS DOCUMENT

This file exists to **preserve the core logic, philosophy, and architecture of the project** when working with LLMs.

Its goal is to prevent:

- loss of context
- architectural drift
- product degradation
- misalignment between technical and cultural layers

**Implementation source of truth:** behavior, APIs, and “what ships today” live in **`/docs/state/`** (maintained per **`/docs/workflow.md`** using **`/prompts/base_task.md`** — state updates are **mandatory** for behavior-changing tasks). This file is **product and design philosophy**, not a substitute for `docs/state/`.

This document must be treated as **source of truth for principles and intent**, not for low-level implementation facts.

---

# 2. PROJECT CORE DEFINITION

This is a:

**Human-centered music streaming platform with integrated cultural layer and blockchain-based economic infrastructure.**

It combines:

- streaming (Spotify-like UX)
- cultural context (journalism + curators)
- fair economics (user-centric model)
- blockchain (invisible settlement layer)

---

# 3. NON-NEGOTIABLE PRINCIPLES

These principles must NEVER be violated.

## 3.1 Music is Human

- The platform prioritizes **human-created music**
- AI is allowed only as a **creative tool**
- Mass-generated AI content is NOT allowed

This is a **core differentiator**

---

## 3.2 Blockchain Must Be Invisible

Users must NEVER see:

- wallets
- tokens
- gas fees

Users only interact with:

- accounts
- subscriptions
- music

Blockchain is ONLY:

- settlement layer
- royalty engine
- ownership infrastructure

---

## 3.3 User Experience = Top Priority

The product MUST feel like:

- Spotify
- Apple Music

NOT like:

- a crypto app
- a complex tool

Constraints:

- play music in <5 seconds
- zero friction onboarding
- no cognitive overload

---

## 3.4 Hybrid Architecture

NEVER put everything on-chain.

Correct separation:

- streaming → CDN
- metadata → database
- logic → backend
- royalties → blockchain

---

## 3.5 Fair Artist Economy

Core rule:

**Artists must earn significantly more than current platforms (~4× Spotify).**

Model:

- subscription-based
- user-centric distribution

---

## 3.6 Transparency by Design

Artists must see:

- streams
- revenue per stream
- splits
- payouts

---

## 3.7 Culture is First-Class

The platform is NOT just a player.

It must include:

- curators
- journalism
- interviews
- reviews
- scenes

Goal:

**restore music as culture**

---

# 4. SYSTEM MENTAL MODEL

Think of the platform as **4 interacting systems**:

## 4.1 Streaming System
- playback
- catalog
- search
- playlists

## 4.2 Economic System
- subscriptions
- royalty pool
- payouts
- splits

## 4.3 Cultural System
- curators
- articles
- playlists
- scenes

## 4.4 Trust System
- identity
- anti-fraud
- reputation
- verification

ALL decisions must consider impact on ALL systems.

---

# 5. DISCOVERY MODEL (CRITICAL)

Discovery is NOT algorithm-only.

It is a **4-engine system**:

1. algorithm
2. curators
3. community
4. reputation

Constraint:

**No single system can dominate discovery.**

---

# 6. ANTI-SPAM / ANTI-AI STRATEGY

The platform must resist:

- AI music spam
- bot streaming
- content farms

Mechanisms:

- upload fee (refundable)
- upload limits
- human verification
- reputation system
- behavioral analysis
- loop penalties

---

# 7. ECONOMIC MODEL (SIMPLIFIED)

Subscription:

~$10/month

Distribution:

- ~70% artists
- ~20% infra
- ~10% company

User-centric:

Each user pays only for what they listen to.

---

# 8. CORE FORMULA

F = P × A  
rate = F / T  

Modifiers:

- loop penalty
- heavy listener adjustment

---

# 9. BLOCKCHAIN ROLE

Blockchain (Algorand) is used for:

- song identity
- royalty distribution
- asset definition (song_asset)
- optional ownership layer

Important:

**Blockchain is infrastructure, not product.**

---

# 10. SMART CONTRACT MODEL

ONLY 4 contracts:

1. Song Registry → identity
2. Royalty Pool → global funds
3. Stream Settlement → payouts
4. Reputation → scoring

Keep system:

- simple
- auditable
- low-cost

---

# 11. SONG MODEL

Each song has:

- ISRC (industry)
- on-chain ID (hash)

Song = blockchain asset (NOT necessarily NFT)

Contains:

- metadata
- splits
- royalty rules

---

# 12. KEY UX PRINCIPLES

- music first
- minimal interface
- fast playback
- optional depth (credits, articles)
- continuous discovery

The app should feel like:

**a living music library**

---

# 13. GROWTH MODEL

Core loop:

artists → fans → streams → revenue → more artists

Artists are primary growth drivers.

---

# 14. CURATOR ECONOMY

Curators:

- discover music
- create playlists
- produce content

They earn:

- % of streams
- content micropayments

Constraint:

- no hidden payola
- full transparency

---

# 15. REPUTATION SYSTEM

Entities:

- artists
- curators
- listeners

Used for:

- ranking
- visibility
- trust
- anti-fraud

Includes:

- score decay over time

---

# 16. WHAT THIS PROJECT IS NOT

The system must NOT become:

- a crypto-first product
- an NFT marketplace
- an AI content farm
- a social media clone
- a purely algorithmic platform

---

# 17. DECISION FILTER (CRITICAL)

When making ANY decision, evaluate:

1. Does this improve artist income?
2. Does this protect human music?
3. Does this maintain simple UX?
4. Does this increase cultural value?
5. Does this keep blockchain invisible?

If any answer is NO → reconsider.

---

# 18. PRIORITY ORDER

When trade-offs appear:

1. UX simplicity
2. artist economics
3. cultural value
4. system scalability
5. technical elegance

---

# 19. LONG-TERM VISION

Build:

A global platform where:

- music is human
- culture is visible
- economics are fair
- infrastructure is transparent

Final goal:

**Make music cultural again, not just consumable.**

---

# END OF FILE

## Related State
- /docs/state/README.md

## Alignment

- Vision: Human-centered streaming, user-centric model
- State: /docs/state/README.md
