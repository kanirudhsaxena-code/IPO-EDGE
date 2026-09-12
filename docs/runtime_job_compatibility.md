# Runtime compatibility audit — 12 September 2026

Production migration 003 is already applied via PR #2. This audit made no production changes and did not switch credentials.

## Database operation tests
Executed on isolated Neon branch br-blue-bonus-ae3tt4l2 as ipo_edge_runtime. Passed: IPO insert/upsert; checkpoint INSERT RETURNING; evidence insert; subscription/sentiment insert; outcome insert/upsert; assessment insert/upsert; efficacy insert/update; learning hypothesis insert; run-log insert/update; framework and learning reads. All fixture data was rolled back.
V1.0 baseline remains 123 checkpoints and fingerprint 5df3c7fc2ce6e3556a523ddfa03d32fb; zero fixture IPOs remain.
These are representative database-operation tests, not complete network-dependent job runs.

## Workflow/code findings
- daily_ipo_edge.yml runs build_universe.py only, after checking that DATABASE_URL exists.
- build_universe.py consumes a backtest source manifest and writes a JSON file. It does not persist research, checkpoint, outcome or learning state.
- backtest-universe.yml runs discovery, normalization and universe loading weekly and on selected pushes.
- phase4-outcomes.yml and phase6-validation.yml target fixed historical windows, not a general live listing scheduler.
- research_pilot.py targets the July–September validation set, requires 67 rows and explicitly writes V1.0 checkpoints.
- pipeline.build_checkpoint defaults to V1.0 and does not itself apply the V1.1 institutional-demand overlay or mandatory evidence recovery.
- phase5_learning_lab.py reads development results and the learning register; it does not autonomously persist new hypotheses or validation states.
Therefore V1.1 registration and data protection are complete, but full autonomous operation is not established.

## Credential cutover blocker
The available GitHub connector exposes no repository-secret update operation. No authenticated gh CLI or GitHub token was present. No login/password was created or exposed, and DATABASE_URL was not changed. The non-owner capability role remains NOLOGIN.

## Next implementation work
Build a prospective V1.1 runtime entrypoint and idempotent daily orchestration, retaining historical scripts as backtest-only paths. Add current-universe discovery, mandatory evidence recovery, version-aware checkpoint generation, listing/efficacy processing, learning proposal persistence and four-table reporting. Validate that complete flow on an isolated branch before a secure workflow-secret cutover. Do not rerun historical writers against production as a live smoke test.

No framework weights, thresholds, learning adoption or historical checkpoints were changed by this audit.
