# PROJECT_VISION.md

## 0. What This Is

This is not just a music streaming platform.

It is a **human-centered music ecosystem** built on top of programmable infrastructure.

The goal is to redesign:

* how music is discovered
* how artists are paid
* how culture is curated
* how fans participate

This system combines:

* streaming (stable revenue layer)
* ownership (upside & speculation layer)
* reputation (cultural coordination layer)

---

# 1. Core Thesis

## 1.1 The Problem

Modern streaming platforms suffer from:

* extremely low artist payouts
* opaque royalty distribution
* algorithmic monoculture
* lack of cultural context
* massive fraud (bots, farms)
* growing wave of AI-generated spam

Additionally:

> revenue is capped by subscription ARPU (~$10/user)

---

## 1.2 The Opportunity

Music is not just consumption.

It is:

* identity
* culture
* community
* speculation
* participation

The current model ignores most of this.

---

## 1.3 The Vision

> **“Human music, powered by programmable economics.”**

A platform where:

* artists are paid fairly (3–5× current industry)
* music is created and curated by humans
* fans can participate economically
* discovery is cultural, not just algorithmic
* payments are transparent and automatic

---

# 2. Product Philosophy

## 2.1 Invisible Blockchain

Blockchain is **not a feature**.

It is infrastructure.

Users never see:

* wallets
* gas
* tokens

They see:

* account
* subscription
* music

---

## 2.2 Hybrid Architecture

Not everything belongs on-chain.

| Layer           | Technology        |
| --------------- | ----------------- |
| Audio streaming | CDN               |
| Metadata        | Database          |
| Royalties       | Blockchain        |
| Payments        | Fiat + Stablecoin |

---

## 2.3 UX Benchmark

Must match or exceed:

* Spotify
* Apple Music

But improve:

* discovery
* transparency
* artist tools

---

# 3. Economic Model (Streaming Layer)

## 3.1 Subscription Model

| Plan    | Price  |
| ------- | ------ |
| Premium | $10–12 |
| Pro     | $15    |
| Family  | $20    |

No ads.

---

## 3.2 Free Access Model

* 30-day trial
  OR
* limited listening credits (~10h)

No ad-supported tier.

---

## 3.3 Revenue Split

| Destination    | %      |
| -------------- | ------ |
| Artists        | 70–75% |
| Infrastructure | ~20%   |
| Platform       | ~10%   |

---

## 3.4 User-Centric Payments

Each user funds only what they listen to.

Example:

* user pays $10
* $7 goes to artists
* user streams 400 tracks

→ ~$0.017 per stream (~4× Spotify)

---

## 3.5 Minute-Based System

Each plan includes:

* base minutes (e.g. 1500 min)

Base rate:

rate = royalty_pool / base_minutes

---

## 3.6 Soft Cap (Critical)

No hard limit.

Instead:

effective_minutes =
min(M, T) + 0.5 × max(M − T, 0)

This ensures:

* heavy listeners don’t break the system
* payouts remain sustainable

---

## 3.7 Loop Penalty

loop_penalty = 1 / (1 + repetitions)

Prevents:

* bot loops
* artificial inflation

---

## 3.8 Final Payout Formula

payout =
(rate_per_minute)
× (song_duration)
× (loop_penalty)
× (heavy_listener_factor)

---

## 3.9 Fan Weight (Optional Extension)

fan_score = streams_artist / streams_total

payout_bonus = base × (1 + fan_score)

Rewards real fans.

---

# 4. Ownership Layer (Second Engine)

## 4.1 Problem

Streaming revenue is capped.

---

## 4.2 Solution: Tokenized Song Ownership

Each song can issue:

* tokens representing % of royalties

Example:

* 100,000 tokens
* represent 20% of streaming royalties

---

## 4.3 Fan Participation

Fans can:

* buy tokens
* earn royalties
* speculate on success

---

## 4.4 Artist Benefits

* upfront funding
* monetization before streaming scale

---

## 4.5 Flywheel

listen → invest → promote → grow → earn

Fans become promoters.

---

## 4.6 Two Economic Engines

| Engine    | Type        |
| --------- | ----------- |
| Streaming | stable      |
| Ownership | speculative |

---

# 5. Cultural Layer (Human Music)

## 5.1 Positioning

> **Music made by humans, for humans.**

---

## 5.2 AI Policy

Allowed:

* AI as a tool

Not allowed:

* mass-generated AI content

---

## 5.3 Artist Verification

Tier system:

| Tier           | Description      |
| -------------- | ---------------- |
| New            | limited exposure |
| Unverified     | restricted       |
| Verified human | full access      |

Verification signals:

* social presence
* performances
* community validation

---

## 5.4 Anti-Spam Upload System

* upload fee or stake
* release limits by tier
* reputation-based scaling

---

# 6. Curation System

## 6.1 Open but Layered

Not fully open. Not fully closed.

Progressive reputation system.

---

## 6.2 Curator Economy

Curators:

* create playlists
* write articles
* discover artists

Earn:

* % of streams generated

---

## 6.3 Cultural Layer (Journalism)

Curators can publish:

* reviews
* interviews
* essays
* video content

This restores **context in music**.

---

## 6.4 Content Monetization

* micro-payments per read
* stream-equivalent for video

---

# 7. Discovery System (4 Engines)

## 7.1 Algorithm

Personalized recommendations.

---

## 7.2 Curators

Human taste layer.

---

## 7.3 Reputation

Merit-based amplification.

---

## 7.4 Community

Social discovery.

---

## 7.5 Unified Ranking

discovery_score =
algorithm

* curator
* reputation
* community

---

# 8. Reputation System

## 8.1 Entities

* artists
* curators
* listeners

---

## 8.2 Key Principle

Reputation = **real impact**, not raw popularity.

---

## 8.3 Signals

### Artists

* retention
* playlist adds
* growth
* verification

### Curators

* discovery success
* engagement

### Listeners

* early discovery
* playlist quality

---

## 8.4 Decay

Reputation decreases over time.

Prevents monopolies.

---

## 8.5 Effects

Reputation influences:

* visibility
* rewards
* discovery impact

---

# 9. Anti-Fraud System

## Layer 1 — Identity

Proof of human.

---

## Layer 2 — Behavior

Detect:

* loops
* 24h streaming
* anomalies

---

## Layer 3 — Economic Penalties

* reduced payouts
* reduced visibility
* account restrictions

---

# 10. Product Structure

## 10.1 User App

* home
* search
* artist pages
* playlists
* library

---

## 10.2 Artist Dashboard

* upload music
* manage metadata
* splits
* analytics

---

## 10.3 Economic Infrastructure

* royalty distribution
* smart contracts
* token system

---

# 11. Smart Contract Architecture

## Core Contracts

1. Song Registry
2. Royalty Pool
3. Stream Settlement
4. Reputation System

---

# 12. Growth Strategy

## 12.1 Entry Point

Start with:

* electronic
* indie
* producer communities

---

## 12.2 Growth Loop

artists → fans → payouts → more artists

---

## 12.3 Key Insight

> Artists bring users.

---

# 13. Monetization Extensions

## 13.1 Sponsored Discovery

Clearly labeled promotion.

---

## 13.2 Upload Fees

Anti-spam + sustainability.

---

## 13.3 Fan Referral Rewards

Artists earn from fan subscriptions.

---

# 14. Design Tensions (Important)

## 14.1 Simplicity vs Power

* invisible blockchain
* complex backend

---

## 14.2 Open vs Curated

* accessibility vs quality

---

## 14.3 Fairness vs Profitability

* artist payouts vs sustainability

---

## 14.4 Human vs AI

* creativity vs scalability

---

# 15. Open Questions

* how strong should token speculation be?
* how strict should AI filtering be?
* optimal curator incentives?
* reputation gaming edge cases?
* regulatory implications of tokenized royalties?

---

# 16. Final Positioning

This is not:

* “Spotify on blockchain”

This is:

> **A new economic and cultural layer for music.**

A system where:

* music is human
* value is fairly distributed
* discovery is meaningful
* fans participate

---

# 17. One-Line Pitch

> **“Spotify UX + 4× artist payouts + fan ownership.”**
