# V1.1 deployment verification — 13 September 2026

## Deployed

Live operations PR #3 merged as `5d8346dd16dd04fa2905e8027408cfaf46b3e2f0`.
[Change](https://github.com/kanirudhsaxena-code/IPO-EDGE/pull/3) · [Integration run](https://github.com/kanirudhsaxena-code/IPO-EDGE/actions/runs/34747577587).
The final feature commit passed 26 tests in disposable PostgreSQL 17. This includes restricted-role permissions, idempotency, unchanged historical checkpoints, future-evidence rejection, outcome/metrics intake and protection against automatic learning adoption.

Migrations 004–008 applied transactionally to production project frosty-block-19864154, branch br-patient-base-ae7nj6tb, database ipo_edge. Integrity guards passed before and after deployment. No V1.0 checkpoints were modified.

## Verified state

| Item | Result |
|---|---|
| V1.1 registry | FROZEN; production_activation_approved true |
| Learnings 1 and 2 | ADOPTED, adopted_framework_version 1.1 |
| Learning 3 | REJECTED |
| Historical V1.0 count | 123 |
| Historical V1.0 fingerprint | 5df3c7fc2ce6e3556a523ddfa03d32fb |
| Live pilot | Hero Motors Limited, IPO 4676, checkpoint 124 |
| Pilot decision | V1.1 T1_DISCOVERY, NV / NO_ACTION; candidate false |
| Pilot evidence | 10 rows covering all eight research blocks; unresolved critical fields explicitly recorded |
| Repeat submission | UNCHANGED; no duplicate checkpoint |
| Deployment/pilot audit | run_log 42–45; final integrity refresh 45 |

Pilot sources included the [issuer RHP](https://www.heromotors.com/uploads/prospectus/hero-motors-limited-rhp.pdf), [SEBI abridged prospectus](https://www.sebi.gov.in/filings/public-issues/sep-2026/hero-motors-limited-rhp_104395.html), [Zerodha issue page](https://zerodha.com/ipo/439845/) and [IPOji](https://www.ipoji.com/ipo/hero-motors-ipo). The pilot demonstrates safe NV persistence, not completed full-universe research. Discovery run 43 is correctly PARTIAL with single-issue scope. Unknown institutional/final subscription evidence and forecasts were not invented.

## Operating schedule

Existing IPO final-day task updated to the V1.1 runbook, daily 19:00 Asia/Kolkata. Morning task created and enabled for approximately 08:00 Asia/Kolkata daily, starting September 14, covering discovery, research, outcomes, metrics, learning evaluation and monthly audits. Both creation/update responses confirmed success and enabled state. Their first complete scheduled V1.1 runs have not yet been observed; task responses did not supply next_run_time. Do not equate enabled scheduling with verified future execution.

Legacy historical GitHub workflows are now manual only. Optional Python live execution remains manual and requires IPO_EDGE_RUNTIME_DATABASE_URL; no fallback to owner credentials. The primary scheduled path uses existing connected ChatGPT research and Neon, with no paid model API.

## Separate checkpoint-immutability assessment

The prior silent UPDATE/DELETE rules have already been replaced by the approved migration003 ALWAYS trigger, which explicitly rejects UPDATE, DELETE and TRUNCATE. The restricted NOLOGIN runtime role has checkpoint SELECT/INSERT only. These controls preserve records against ordinary runtime mutations; they cannot constrain a database owner who can change DDL.

Remaining enforcement gap: connected owner credentials have not been replaced with a restricted runtime login. Safest next hardening is credential separation: provision a dedicated LOGIN inheriting only ipo_edge_runtime, use it for operational execution, keep owner credentials for separately controlled migrations, and verify grants and attempted mutation on an isolated branch before cutover. Do not grant runtime membership in owner/admin roles. Independently retain historical fingerprints outside the database. No additional schema change or credential cutover was made as part of this recommendation.

The finalized Drive Master Specification V1.1 and production scoring configuration remain unchanged. Follow [LIVE_OPERATIONS_V1.1.md](LIVE_OPERATIONS_V1.1.md) for execution and partial/failure reporting.
