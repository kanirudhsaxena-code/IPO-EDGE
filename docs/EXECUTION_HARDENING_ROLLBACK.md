# IPO EDGE V1.1 Execution Hardening — Rollback Plan

Scope: `ipo-execution-hardening-v1.1` only. Production `main` and frozen IPO EDGE V1.1 model/history remain authoritative until an explicit governed merge/activation approval.

## Pre-merge / shadow rollback

1. Disable all execution-hardening feature flags / master switch in `config/execution_hardening_v1.1.json`.
2. Stop shadow/replay invocation. Do not copy shadow/replay artifacts into canonical production tables or efficacy populations.
3. Leave production `main`, canonical historical checkpoints, outcomes, scoring, grades, thresholds, NV gate and recommendation policy untouched.
4. Preserve failed-run diagnostics and immutable evidence for audit; do not rewrite or backdate T2.

Because hardening is additive and fail-closed, pre-merge rollback is removal/disablement of the shadow execution path, not a data migration.

## Post-merge rollback boundary

No production merge or activation is authorized by this document. If explicit user approval is later granted and a hardening-only merge is activated, rollback must revert only the categorized execution/infrastructure commits introduced by that approved merge. Before any revert, verify that the revert does not alter frozen model-rule files or historical checkpoint/outcome data.

If safe selective revert cannot be proven, fail closed: disable the hardening feature flags and keep the existing production model behavior rather than attempting a destructive rollback.

## Mandatory rollback verification

After rollback/disablement, require all of the following before declaring recovery:

- production model-rule fingerprint/lock tests pass;
- frozen-history fingerprint/append-only tests pass;
- same evidence produces the same V1.1 score, grade and decision;
- production writes from hardening remain disabled unless separately approved;
- no canonical checkpoint or outcome was deleted, edited or backdated;
- unresolved critical evidence remains NV after recovery exhaustion;
- Upstox/provider failure remains nonfatal to the canonical run.

Any failed verification keeps the system fail-closed and blocks production activation.
