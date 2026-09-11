# IPO EDGE Master Specification V1.0

**Status:** FROZEN CANONICAL SPECIFICATION  
**Command:** `IPO EDGE`

## Purpose
Autonomous Indian IPO discovery, research, scoring, recommendation, outcome tracking, missed-opportunity analysis, continuous learning, and efficacy measurement.

## Operating principles
1. **Independence:** no routine user inputs required.
2. **Evidence policy:** only deep, current, verifiable web research. Critical unverifiable evidence = `NV`, blocking A+/A++.
3. **Full-universe tracking:** all eligible Indian Mainboard and SME IPOs enter the Master IPO Ledger.
4. **Historical integrity:** recommendation checkpoints are immutable; listing outcomes never alter prior grades.
5. **Simple output, sophisticated engine:** standard output is four compact tables.

## End-to-end process
`DISCOVER -> RESEARCH -> SCORE -> REASSESS -> RECOMMEND -> TRACK -> LISTING OUTCOME -> ASSESS -> IDENTIFY MISSES -> LEARN -> VALIDATE -> VERSION -> REPEAT`

## Research blocks
- **R1 Business:** business model, market position, growth opportunity, competitive advantage, risks.
- **R2 Financials:** revenue/profit growth, margins, ROE/ROCE, debt, cash flow, working capital, earnings quality.
- **R3 Valuation:** issue valuation, listed peers, growth/profitability context, listing-upside room.
- **R4 Promoter & Issue:** promoter/governance, fresh issue vs OFS, use of proceeds, dilution.
- **R5 Analyst Research:** reputable broker/analyst views and dates.
- **R6 Institutional Evidence:** anchor book, QIB level, QIB acceleration, institutional quality.
- **R7 Market Demand:** Total/NII-HNI/Retail subscription, GMP level/trend, demand quality.
- **R8 Environment:** sector, IPO-market and broader market/macro regime.

## Source hierarchy
1. DRHP/RHP/company filings/exchange/regulator disclosures
2. NSE/BSE/official anchor and IPO disclosures
3. Reputable brokerage/institutional research
4. Reputable financial media
5. Established IPO-data aggregators for cross-checking
6. GMP sources as secondary sentiment evidence only

Material unresolved conflicts must be marked `NOT_VERIFIED`.

## 100-point scoring model
- Business Quality: 15
- Financial Quality: 15
- Valuation: 20
- Institutional Conviction (QIB + anchors): 20
- Market Demand / Subscription: 10
- Analyst Consensus: 10
- Sector / IPO-Market Environment: 5
- GMP Confirmation: 5

## Grades
- **95–100:** A++ = Strong Subscribe
- **90–94:** A+ = Subscribe
- **85–89:** A = Track only
- **<85:** Reject
- **Critical evidence missing:** NV

Hard blockers can cap grade below A+ regardless of numerical score.

## Immutable checkpoints
- **T1 Discovery Grade** — earliest meaningful research-based assessment.
- **T2 Final Subscription-Day Grade** — canonical final pre-listing assessment used for efficacy.
- **T3 Listing Outcome** — verified listing result, recorded only after T2 is frozen.

Intermediate checkpoints may be added when material evidence changes.

## Evidence Delta
Every reassessment stores new evidence, prior/current score and grade, upgrade/unchanged/downgrade, and reason. Earlier checkpoints remain unchanged.

## Missed opportunity
A missed opportunity is an IPO not rated A+/A++ at T2 that achieves **>=20% actual listing gain**.

## Outcome classes
- Recommended + >=20% = Strong Hit
- Recommended + 0–19.99% = Positive/Moderate Hit
- Recommended + <0% = False Positive
- Not recommended + >=20% = Missed Opportunity
- Not recommended + <20% = Correct Avoidance

## Mandatory efficacy metrics
Positive Recommendation Hit Rate; >=20% Recommendation Hit Rate; A++ Hit Rate; A+ Hit Rate; Opportunity Capture Rate; Miss Rate; False Positive Rate; Correct Avoidance Rate; Average Actual Listing Gain of Recommendations; Average Estimated Gain; Forecast Error; Final-Day Upgrade Hit Rate.

No single opaque efficacy score is used.

## Continuous learning
`MISS / ERROR -> IDENTIFY PRE-LISTING SIGNAL -> FORM HYPOTHESIS -> BACKTEST -> VALIDATE ON UNSEEN PERIOD -> REJECT OR VALIDATE -> PROPOSE CHANGE -> ADOPT IN NEW VERSION -> MEASURE FORWARD PERFORMANCE`

Learning states: `TESTING`, `VALIDATED`, `ADOPTED`, `REJECTED`. Rejected learnings remain stored. One missed IPO never justifies an automatic rule/weight change.

## Initial backtest
- **Study period:** 1 Apr 2026–10 Sep 2026
- **Development:** 1 Apr 2026–30 Jun 2026
- **Validation:** 1 Jul 2026–10 Sep 2026

Rules: reconstruct only contemporaneous pre-listing evidence; freeze T1/T2 before revealing T3; prevent outcome leakage; preserve source dates; validate learnings out of sample where feasible.

## Standard output: four tables
1. **Efficacy Assessment**
2. **Missed Opportunities**
3. **Continuous Learnings**
4. **Current Opportunities**

Only A+/A++ are actionable. A near-candidates may be surfaced compactly.

## Persistent architecture
- **Neon Postgres:** system of record for machine-readable state
- **Google Drive:** human-readable canonical Master Specification and major reports
- **GitHub:** code, migrations, scoring config, tests, workflows
- **Scheduled jobs:** discovery, final-day reassessment, listing outcomes, learning evaluation, integrity audits

## Core Neon entities
`framework_versions`, `ipos`, `research_evidence`, `checkpoints`, `subscription_snapshots`, `market_sentiment_snapshots`, `listing_outcomes`, `assessments`, `learnings`, `efficacy_snapshots`, `run_log`.

## Automation safeguards
- No automated framework weight/threshold changes.
- Every run writes to `run_log`.
- Source URLs and retrieval timestamps are preserved.
- Failed/incomplete research cannot silently produce A+/A++.
- Historical checkpoints are append-only.
- Schema migrations are versioned.

## Release gates
An A+/A++ recommendation requires verified critical evidence, reproducible score/grade, no unresolved material blocker, known framework version, and source dates preceding the checkpoint.

A backtest cannot be released until universe completeness, pre-listing cutoffs, no outcome leakage, development/validation split, and missed-opportunity analysis are all checked.

## Canonical Drive document
https://docs.google.com/document/d/1uclQCT35NXz0r95I9mfrqlwrMAsgKrH-k6tsbUupGi4
