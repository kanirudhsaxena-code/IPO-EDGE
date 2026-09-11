# IPO EDGE

Autonomous Indian IPO research, scoring, recommendation, backtesting, efficacy tracking, missed-opportunity analysis, and continuous-learning framework with Neon persistence and automated workflows.

## Canonical framework
- Version: 1.0
- Status: Frozen
- Command: `IPO EDGE`
- Google Drive master specification: https://docs.google.com/document/d/1uclQCT35NXz0r95I9mfrqlwrMAsgKrH-k6tsbUupGi4
- Neon project: `IPO EDGE V1`
- Neon database: `ipo_edge`

## Core principles
- Deep, current, verifiable web research only
- Full IPO-universe tracking across Mainboard and SME
- Immutable T1/T2 recommendation checkpoints
- Listing outcomes separated from pre-listing decisions
- Only A+ / A++ are actionable
- Missed opportunity = final pre-listing grade below A+ with actual listing gain >=20%
- Continuous learning must be validated before framework adoption

## Repository layout
- `spec/` — frozen framework specification
- `config/` — scoring and decision rules
- `db/migrations/` — Neon schema migrations
- `src/` — discovery, research, scoring, checkpoints, outcomes, efficacy, learning, reporting
- `tests/` — framework and data-integrity tests
- `.github/workflows/` — automation workflows
