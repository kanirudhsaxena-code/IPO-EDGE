# IPO EDGE V1.1 — Execution Hardening Build

Status: ACTIVE SEPARATE BUILD
Branch: `ipo-execution-hardening-v1.1`
Production baseline: `main` / IPO EDGE V1.1
Model policy: FROZEN — no scoring, weight, grade, threshold, NV-gate, or decision-rule changes.
Historical policy: existing checkpoints/outcomes remain immutable; no historical rewrite or backdating.

## Objective
Make the existing IPO EDGE V1.1 run completely, consistently, on time, with maximum verified evidence and minimum avoidable NV/PARTIAL outcomes while preserving identical model behavior for identical evidence.

## Ownership model
- ChatGPT Executor: code changes, source orchestration, diagnostics, tests, replay tooling, documentation, CI triage, acceptance evidence, and status updates.
- GitHub Actions: automated unit/integration/regression checks and artifact generation.
- Neon: separate hardening test schema/branch when provisioned; production writes are prohibited until acceptance.
- User: only account-level actions that cannot be performed by the executor, such as granting/refreshing an external credential or explicitly approving production merge/activation.
- Upstox: read-only external data provider; must never be a single point of failure.

## Timeframe convention
The executor runs hourly. Targets are expressed in executor cycles rather than calendar promises.

## Build checklist

### EH-00 — Guardrails and isolation
- [x] Isolated hardening branch; frozen scope; model/history guard tests; fail-closed rollback switches.

### EH-01 — Current-run forensic baseline
- [ ] Live NV/PARTIAL/miss classification (tooling committed; awaits Neon read access).
- [ ] Reconcile 123 frozen T2 population (query committed; awaits Neon read access).
- [ ] Record live baseline rates (collector committed; awaits Neon read access).
- [x] Model-related misses tagged DEFERRED only; no model change.

### EH-02 — Universe discovery hardening
- [ ] Live source union across NSE/BSE/SEBI/Upstox/approved specialist calendars; reconciliation/provider cores committed, live verified enumeration pending.
- [x] Mainboard and SME reconcile independently.
- [x] Explicit enumeration/completeness required.
- [x] Source outage/empty parse fails closed unless independent sources prove scope.
- [x] Per-source health/discrepancy logging.

### EH-03 — Canonical identity resolver
- [ ] Live canonical identity map; resolver/ingress/feed builder committed, actual fetched live/shadow provider feed evidence pending.
- [x] Preserve historical names; aliases only.
- [x] Detect duplicates/variants/malformed records before persistence.
- [x] Known-variant tests.

### EH-04 — Upstox read-only provider
- [x] Feature-flagged fail-closed provider.
- [ ] Credential-backed live IPO discovery/details evidence pending.
- [x] Read-only allow-list only.
- [x] Never sole critical-evidence proof.
- [x] Outage does not stop EDGE.
- [x] Missing credential explicit/nonfatal.

### EH-05 — Deterministic R1–R8 recovery ladder
- [x] Preferred/fallback source order per block.
- [x] Two independent attempts for unresolved critical R2/R3/R4/R6/R7 before NV recovery exhaustion.
- [x] 401/403/CAPTCHA routes stopped; legitimate alternatives only.
- [x] Provenance group/independence basis persisted.
- [x] Fetch/parse/verification states separated.
Evidence: `scripts/execution_hardening_recovery.py`, `tests/test_execution_hardening_recovery.py`; CI #330 PASS.

### EH-06 — Research-priority routing (non-model)
- [x] Operational RESEARCH_PRIORITY only; no model-output change.
- [x] Verified partial signals route retrieval effort only.
- [x] Guard proves routing cannot bypass NV/hard blockers.
Evidence: `scripts/execution_hardening_research_priority.py`, tests; CI #330 PASS.

### EH-07 — Final-day/T2 reliability
- [ ] Closing-day live universe/source reconciliation wiring pending; deterministic plan committed.
- [x] Final subscription timing after 19:00 Asia/Kolkata.
- [x] Existing V1.1 verified-final requirement preserved.
- [x] No retrospective/backdated T2.
- [x] Explicit missed/unresolved reason codes.
Evidence: `scripts/execution_hardening_t2.py`, tests; CI #330 PASS.

### EH-08 — Observability and console diagnostics
- [ ] Expose per-run expected/reconciled/researched/complete/NV/PARTIAL counts. Implementation committed `f94db57`; tests committed `27d9ee1`; awaiting CI before formal close.
- [ ] Show per-IPO unresolved blocks, attempted sources, conflicts, identity status, and final disposition. Implementation/tests committed; awaiting CI.
- [ ] Show source health and Upstox availability separately from framework efficacy. Implementation/tests committed; awaiting CI.
- [ ] Separate canonical efficacy from execution diagnostics and replay/counterfactual analysis. Explicit separate payload kinds committed; awaiting CI.
Acceptance: a PARTIAL/NV result is immediately diagnosable without reading raw receipts.

### EH-09 — Shadow replay and regression
- [ ] Replay frozen historical cases under hardened execution without future-data leakage.
- [ ] Keep canonical historical outcomes unchanged.
- [ ] Verify same evidence => same V1.1 model output.
- [ ] Measure reductions in retrieval-driven NV/PARTIAL, identity errors, universe gaps and missed T2s.
- [ ] Flag model-related misses as DEFERRED, not fixed.

### EH-10 — Prospective shadow run
- [ ] Prospective alongside production rules after EH-00–EH-09 pass.
- [ ] Isolated test/shadow storage only.
- [ ] Compare coverage/completeness/timing/decision invariance.

### EH-11 — Merge readiness
- [ ] Categorized execution-only merge diff.
- [ ] Prove zero model-rule changes.
- [ ] Prove zero frozen-history mutation.
- [ ] Document rollback.
- [ ] Request explicit user approval before production merge/activation.

## Hard blockers / user-action dependencies
Current transient dependency: Neon read-only SQL project resolution remains unavailable for live EH-01. This does not block repository hardening.
Current EH-04 dependency: credential-backed Upstox live transport/discovery evidence unavailable. This does not block independent hardening.

## Non-negotiable acceptance gates
1. Zero model-rule changes.
2. Zero historical checkpoint/outcome mutation.
3. Same evidence => same V1.1 score, grade and decision.
4. Mainboard and SME coverage demonstrated before COMPLETE.
5. Upstox failure cannot stop the run.
6. Critical missing evidence remains NV after recovery exhaustion.
7. No backdated T2 and no future-data leakage.
8. Canonical efficacy remains separate from execution diagnostics/replays.
