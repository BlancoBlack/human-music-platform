Type: ARCHITECTURE
Status: UNKNOWN
Linked State: /docs/state/backend.md
Last Verified: 2026-04-29

# Architecture (merged)

## Source: root architecture.md

# ARCHITECTURE.md

# 1. System Overview

The platform uses a **hybrid architecture** combining:

- Web2 infrastructure (performance)
- Blockchain (trust + settlement)

---

# 2. Architecture Layers

| Layer | Responsibility |
|------|--------|
| Frontend | User interface |
| Backend API | Application logic |
| Database | Metadata & analytics |
| Audio Services | Streaming |
| Blockchain | Royalties & ownership |

---

# 3. High-Level Flow

1. User opens app
2. Frontend requests data
3. Backend returns recommendations
4. User plays track
5. Audio served via CDN
6. Stream event recorded
7. Event processed
8. Smart contract executes payout

---

# 4. Frontend

Technologies:
- React (web)
- Next.js
- React Native (mobile)

Responsibilities:
- playback
- navigation
- discovery
- search
- social interactions

---

# 5. Backend

Technologies:
- Python
- FastAPI
- PostgreSQL

Responsibilities:

- authentication
- user profiles
- music catalog
- playlists
- recommendations
- search
- stream event logging

---

# 6. Database

Primary DB:
PostgreSQL

Stores:

- users
- artists
- songs
- albums
- playlists
- social graph
- listening history
- analytics

---

# 7. Audio Infrastructure

Architecture:

storage → CDN → user

Requirements:

- low latency
- high availability
- global scalability

---

# 8. Stream Event System

Each play generates:

- stream_event
- user_id
- song_id
- timestamp
- duration

Used for:

- royalty calculation
- recommendations
- analytics

---

# 9. Recommendation Engine

Inputs:

- listening history
- skips
- saves
- playlists
- audio features

Outputs:

- Discover Weekly
- Daily Mix
- Hidden Gems

Hybrid signals:

- algorithmic
- curator-based
- social
- reputation

---

# 10. Blockchain Layer (Algorand)

Used for:

- song identity
- royalty distribution
- asset ownership
- reputation signals

---

# 11. Smart Contracts

## 11.1 Song Registry Contract

Stores:

- song_id
- algorand_asset_id
- ISRC
- splits
- verification status

Purpose:
identity only (no money)

---

## 11.2 Royalty Pool Contract

Handles:

- subscription revenue
- global royalty pool

---

## 11.3 Stream Settlement Contract

Core logic:

stream_value =
rate_per_minute
× duration
× loop_penalty
× heavy_listener_factor

Executes micropayments.

---

## 11.4 Reputation Contract

Stores:

- artist_score
- curator_score
- user_score
- verification status

Affects:

- visibility
- payouts
- limits

---

# 12. Song Identity

Dual system:

- ISRC (industry standard)
- On-chain Song ID (hash)

---

# 13. Song Asset Model

Each song = blockchain asset

Contains:

- metadata
- splits
- royalty rules

Not necessarily tradable NFT.

---

# 14. Payments Flow

1. User pays (FIAT)
2. Platform converts to USDC
3. Funds go to royalty pool
4. Smart contracts distribute payouts

---

# 15. Upload System

Flow:

1. upload WAV
2. cover art
3. metadata
4. credits
5. splits

---

# 16. Upload Fee System

Cost: €2

- €1.5 refundable
- ~€0.002 blockchain cost
- remainder platform + curators

Purpose:

- anti-spam
- sustainability

---

# 17. Publishing Limits

| Artist Tier | Limit |
|------------|------|
| New | 2/month |
| Verified | 5/month |
| Established | 10/month |

Credits accumulate.

---

# 18. Anti-Fraud System

## 18.1 Identity Layer

- proof of personhood
- optional integrations:
  - Worldcoin
  - Gitcoin Passport
  - BrightID

---

## 18.2 Behavioral Analysis

Detects:

- loops
- 24h streaming
- abnormal patterns

---

## 18.3 Economic Penalties

- reduced payouts
- visibility reduction
- account freeze
- stake loss

---

# 19. Discovery System Architecture

Four engines:

1. algorithm
2. curators
3. community
4. reputation

---

# 20. Curator Infrastructure

Curators have:

- profile
- playlists
- articles
- videos

Monetization:

- % of streams
- micropayments for content

---

# 21. Content System

Supports:

- text (articles)
- video
- embedded tracks

Micropayments:

- per read
- per view

---

# 22. Sponsored Discovery

Clearly labeled.

Rules:

- transparency
- no hidden promotion
- anti-manipulation checks

---

# 23. Observability

Metrics:

- streams/sec
- latency
- API errors
- fraud signals

Tools:

- Prometheus
- Grafana
- Elastic

---

# 24. Scalability

Designed for:

- 100k users
- 1M users
- 10M users

Scaling methods:

- CDN
- DB replication
- microservices

---

# 25. Security

- encrypted data
- secure auth
- wallet protection
- smart contract audits

---

# 26. Roadmap

## Phase 0 — Concept

- UX prototype
- artist interviews

---

## Phase 1 — MVP

- upload
- playback
- playlists
- search

---

## Phase 2 — Economy

- royalties
- smart contracts
- splits

---

## Phase 3 — Discovery

- algorithm
- reputation
- ranking

---

## Phase 4 — Social

- follow system
- activity feed

---

## Phase 5 — Culture

- articles
- interviews
- video

---

## Phase 6 — Ownership

- tokenized songs
- fan participation

---

# 27. Final System Vision

A fully integrated platform combining:

- streaming
- economic infrastructure
- cultural layer
- decentralized ownership

---

End of Architecture Document

## Source: /architecture/architecture.md

<!-- model: claude -->
# Architecture

This project follows an event-driven architecture.

# Architecture Rules

execution_routing.md has priority over this file

---

# Flow

Frontend → API → Service → Database → Event → Worker → Blockchain

---

# Backend Layers

api → HTTP layer  
services → business logic  
models → database schema  
events → event emission  
workers → async processing  
blockchain → external integration

---

# Rules

- No business logic in API routes
- No blockchain calls in routes
- All side effects go through events
- Workers execute async logic

---

# Blockchain

Algorand is used only for:

- transaction simulation
- future royalty logic

---

# Current Limitation

Event system is synchronous (in-process)

Future:

- Redis / queue system

## Related State
- /docs/state/backend.md

## Alignment

- Vision: Human-centered streaming, user-centric model
- State: /docs/state/backend.md
