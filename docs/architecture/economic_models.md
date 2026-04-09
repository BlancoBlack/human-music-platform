# ECONOMIC MODELS — HARD RULES (DO NOT BREAK)

## ⚠️ CRITICAL: TWO DIFFERENT ECONOMIC MODELS EXIST

This project intentionally contains **TWO SEPARATE ECONOMIC MODELS**.

They MUST NEVER be mixed.

---

# 1) USER MODEL (OUR SYSTEM — CORE PRODUCT)

## 🔥 THIS IS THE CORE OF THE PLATFORM

This is the **real economic engine** of the project.
Everything important (fairness, payouts, value proposition) depends on this.

## Main file

* `payout_service.py` ✅ **CORE FILE — DO NOT BREAK**

## Purpose

Fair, anti-fraud, user-centric payout system.

## Data sources

* ListeningAggregate
* ListeningEvent

## Fields used

* validated_duration
* weight
* weighted_duration

## Logic

* Uses validation + anti-spam weighting
* Penalizes repeated listens
* Invalid listens contribute 0

## Where used

* payout_service.py → calculate_user_distribution()
* Worker (listen_worker.py)
* Real payout generation
* Earnings logic

## Rule

✔ ALWAYS use:

* validated_duration
* weight
* weighted_duration

❌ NEVER fallback to raw duration for payouts

❌ NEVER modify this logic casually — this is the PRODUCT

---

# 2) GLOBAL MODEL (SPOTIFY-LIKE — COMPARISON ONLY)

## ⚠️ THIS IS ONLY FOR DISPLAY / COMPARISON

This model exists ONLY to:

* compare against traditional platforms
* show value to users
* power dashboard narratives

## Main file

* `pool_payout_service.py` ⚠️ **COMPARISON ONLY — NOT CORE**

## Purpose

Simulate traditional streaming platforms (Spotify, Apple Music, etc.)

## Data sources

* GlobalListeningAggregate

## Fields used

* total_duration ONLY

## Logic

* NO validation
* NO weighting
* Pure proportional distribution

## Where used

* pool_payout_service.py → calculate_global_distribution()
* comparison_service.py
* artist dashboard "Global Model Comparison"

## Rule

✔ ALWAYS use:

* total_duration

❌ NEVER use:

* weight
* validated_duration
* weighted_duration

❌ NEVER try to "improve" this model — it must stay dumb and raw

---

# 🚨 ABSOLUTE PROHIBITIONS

## NEVER DO THIS:

❌ Use weighted_duration inside Global model
❌ Use total_duration inside User payout logic
❌ Modify payout_service.py using Global model logic
❌ Modify pool_payout_service.py using User model logic
❌ Mix user-scoped and global-scoped pools
❌ Apply anti-fraud logic to Global model

---

# 🧠 DESIGN PRINCIPLE

USER MODEL = product (truth, fairness, innovation)
GLOBAL MODEL = benchmark (reference, comparison, narrative)

They are compared, NOT merged.

---

# 🔍 BEFORE CHANGING ANY ECONOMIC CODE

You MUST ask:

1. Am I modifying `payout_service.py` (CORE)?
   → then use weighted logic ONLY

2. Am I modifying `pool_payout_service.py` (COMPARISON)?
   → then use raw total_duration ONLY

3. Am I mixing both?
   → STOP immediately (this is a bug)

---

# 🎯 GOAL

* Keep models clean and independent
* Ensure comparisons are meaningful
* Protect core payout system integrity

---

# 🚫 VIOLATION CONSEQUENCE

Breaking these rules will:

* Corrupt payouts (CRITICAL)
* Break dashboard comparisons
* Destroy product credibility

---

# FINAL RULE

IF YOU TOUCH ECONOMIC LOGIC:

→ You MUST explicitly state:

* which file
* which model (USER or GLOBAL)

If not, DO NOT PROCEED.
