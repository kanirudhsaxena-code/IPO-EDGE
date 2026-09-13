# Source resilience review package — 13 September 2026

Implementation is isolated in [draft PR #4](https://github.com/kanirudhsaxena-code/IPO-EDGE/pull/4). Production code, functions, runbook and automations are unchanged. This extends the existing agent; no parallel scheduler or database is introduced.

## Exact file manifest

Modified:
- src/ipo_edge/sources.py
- src/ipo_edge/live_sources.py
- src/ipo_edge/live_policy.py
- src/ipo_edge/live_runtime.py
- src/ipo_edge/live_report.py
- scripts/run_live.py
- tests/test_live_runtime.py
- tests/test_live_postgres.py
- .github/workflows/live_runtime_tests.yml
- docs/LIVE_OPERATIONS_V1.1.md

New:
- config/source_execution_v1.1.json
- src/ipo_edge/source_orchestration.py
- tests/test_source_orchestration.py
- db/migrations/009_source_execution_validation.sql
- db/rollback/009_source_execution_validation.sql
- docs/SOURCE_RESILIENCE_REVIEW.md

## Database impact

Function-only migration009 adds validate_ipo_edge_recovery, validate_ipo_edge_final and finalize_ipo_edge_cycle, and replaces apply_ipo_edge_research with the previous scoring implementation plus execution validation. All use SECURITY INVOKER and restricted EXECUTE grants. No table, column, enum, credential or historical-data migration. Existing migrations001–008 are unchanged.

Latest migration was installed successfully on isolated Neon branch br-blue-bonus-ae3tt4l2. The rollback restored the previous intake definition successfully, then the new definition was reinstated. Isolated V1.0 remained 123 / 5df3c7fc2ce6e3556a523ddfa03d32fb throughout. Production read-only checks returned the same baseline and showed migration009 absent. Learnings1/2 remain ADOPTED in1.1 and3 REJECTED.

## Validation

53 local tests pass; six PostgreSQL integration tests execute in GitHub CI. Review the latest commit's integration result on PR#4 before merging. Tests cover transient BSE failures, access challenges/cooldowns, BSE/NSE/both unavailable, independent recovery, missing segments, date conflicts, verified-empty versus false-empty, syndicated sources, per-block recovery, future evidence, all four final subscription fields, T2 boundaries, omitted active ledger entries, idempotency and V1.0 integrity. Existing scoring/overlay/learning tests remain in the suite.

Read-only live smoke: main BSE publication returned403; a BSE SME alternate and SEBI remained accessible; NSE returned content but automated calendar coverage was unverifiable. The cycle continued and reported PARTIAL/DEGRADED. Follow-up parser checks recovered both independent calendar tables: [IPO Markets](https://ipomarkets.com/ipo-calendar/september-2026) returned39 rows (20 Mainboard/19 SME), [IPO Watch](https://ipowatch.in/ipo-calendar-september-2026/) returned46 (22 Mainboard/24 SME). A full-month September parsing defect was repaired with a regression test.

These differing enumerations are a real unresolved coverage issue, not a success claim. The autonomous ChatGPT research path must reconcile omissions, identities and dates through issue-specific evidence before reporting COMPLETE. No production IPO research/checkpoints were added by these smoke tests.

## Execution limits and approval boundary

The Python scraper remains a conservative numeric helper. It records targeted recovery attempts but does not pretend numeric extraction constitutes qualitative R1–R8 verification. Scheduled ChatGPT performs that review using the same receipt contract and Neon validators. Source lineage and official publication interpretation require evidence-backed research; structural validators cannot prove the truth of external publications.

The approved clarification separates individual publication health from research coverage. Execution-connector outages or unestablished segment coverage still produce PARTIAL/FAILED. Successful source download alone is insufficient. The approved critical set, scores, thresholds, candidate behavior and learning statuses are unchanged. No retrospective T2, new framework version, paid API, credentials or trading execution.

After deployment approval, update the existing Morning/Final-Day prompts to the revised runbook and require finalize_ipo_edge_cycle for parent-cycle completion. Preserve existing schedules and safeguards. Actual automation changes have not yet been made.

## Rollback

Use discovery-only shadow mode to stop operational writes while investigating. Pin previous code/runbook and task instructions to 8ae6661fbad81c3c039f5657a2cd143c30bd9b96. Restore intake with db/rollback/009_source_execution_validation.sql; the rollback was exercised on the isolated branch. Never restore the whole database, delete receipts, alter historical checkpoints or backdate missed T2. New validators may safely remain unused after code rollback.

## Deployment sequence after review

1. Confirm final CI on the exact PR head and fixed production baseline.
2. Merge only after the requested user review.
3. Apply migration009 transactionally with before/after integrity guards.
4. Update existing automation prompts; no new jobs or secrets.
5. Run a bounded production cycle, persist actual coverage/failures and verify history again.
6. Report COMPLETE only if reconciliation and evidence gates pass. Source availability or enabling a schedule is not proof of a completed autonomous cycle.
