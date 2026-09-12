# Checkpoint immutability validation — 12 September 2026

## Scope and result
Migration 003 was applied only to IPO EDGE V1 test branch `br-blue-bonus-ae3tt4l2` (`test-checkpoint-immutability-20260912`), cloned from production `br-patient-base-ae7nj6tb`. Database: `ipo_edge`. Production has not been changed.

The existing UPDATE/DELETE rules silently suppress mutations. Migration 003 atomically replaces them with an ALWAYS-enabled statement trigger raising SQLSTATE 55000 for UPDATE, DELETE, and TRUNCATE. Normal inserts remain allowed. No checkpoint rows are rewritten.

## Executed checks
- Owner UPDATE, DELETE and TRUNCATE CASCADE: each rejected with 55000.
- Owner INSERT RETURNING: succeeded; fixture rolled back.
- Non-owner runtime SELECT and INSERT RETURNING: succeeded; fixture rolled back.
- Runtime UPDATE, DELETE and TRUNCATE CASCADE: each rejected with 42501.
- Temporary test membership was revoked.
- Zero ISOLATED_TEST fixture rows remain.
- Test and production both retain 123 V1.0 checkpoints.
- Both fingerprints exactly match the pre-change baseline: `5df3c7fc2ce6e3556a523ddfa03d32fb`.
- Production still has its two original rewrite rules, no new trigger, and no ipo_edge_runtime role.
- Test trigger is enabled ALWAYS; original rules are removed on test only.

Tests are in tests/checkpoint_immutability.sql and are intended exclusively for an isolated branch. Use psql ON_ERROR_STOP and a transaction. The executed owner and runtime DO blocks are the same blocks committed in that test file.

## Runtime role boundary
ipo_edge_runtime is a NOLOGIN capability role, with no owner membership or schema CREATE grant. It grants only SELECT/INSERT on checkpoints and sequence USAGE. Explicit operational grants support existing IPO, outcome, assessment and run-log paths. Framework registration and learning-status updates remain administrative. It is not yet a production login and existing workflow credentials are unchanged. Full autonomous job compatibility has not been certified.

## Production rollout after review
1. Apply migration 003 in one transaction, with its lock timeout. It is a one-time migration, not an idempotent repair script.
2. Perform read-only trigger/role/config and historical fingerprint checks. Never run mutation tests against production.
3. Provision a dedicated non-owner runtime login through a secure credential channel, grant the runtime capability, and verify it cannot assume the owning role.
4. Review grants per scheduled job, particularly learning evaluation; test actual jobs on the isolated branch before switching workflow credentials.
5. Switch runtime credentials only after those tests pass. Keep owner credentials separate for approved administrative work.

Owner/admin access can still alter or remove guards; this is not protection against a malicious administrator. Restricting runtime identity is therefore a separate required cutover.

## Recovery
Keep existing owner credentials during rollout. If application compatibility fails, stop affected jobs and revert the credential cutover while investigating; retain checkpoint guards. A schema rollback, if needed, must be separately reviewed and restore both original rules atomically before removing the trigger/function. Never undo protection by deleting or rewriting checkpoint data.

The test branch is retained for review. No production schema changes, GitHub merge, or credential rotation has occurred.
