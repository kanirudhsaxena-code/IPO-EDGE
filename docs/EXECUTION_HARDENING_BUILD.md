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
The executor runs every 4 hours. Targets are expressed in executor cycles rather than calendar promises.

## Build checklist

### EH-00 — Guardrails and isolation
Owner: ChatGPT Executor
Target: Cycle 1
- [x] Create isolated GitHub branch `ipo-execution-hardening-v1.1`.
- [x] Freeze model-change scope in this build document.
- [x] Add automated guard test: identical evidence must produce identical V1.1 score/grade/decision. Evidence: `tests/test_execution_hardening_model_lock.py`.
- [x] Add test preventing modification of frozen historical V1.0/V1.1 checkpoint fixtures. Evidence: `tests/test_execution_hardening_history_lock.py` plus existing isolated-DB `tests/checkpoint_immutability.sql`.
- [x] Define rollback switch for every new provider/orchestrator change. Evidence: `config/execution_hardening_v1.1.json` and `tests/test_execution_hardening_switches.py`; all hardening features are fail-closed/off by default and production writes are disabled.
Acceptance: no model-rule diff; no historical mutation path.

### EH-01 — Current-run forensic baseline
Owner: ChatGPT Executor
Target: Cycles 1–2
- [ ] Classify existing NV/PARTIAL/missed cases by execution cause: retrieval, identity, timing, conflict, universe, infrastructure, or model-related/deferred. Tooling committed: `scripts/execution_hardening_forensics.py`; taxonomy tests: `tests/test_execution_hardening_forensics.py`. Live classification awaits database read access.
- [ ] Reconcile the 123 frozen T2 population against assessed rows and identify any unresolved/pending records. Read-only reconciliation query committed; live execution awaits database read access.
- [ ] Record current baseline rates: universe completion, critical-block completion, T2 completion, NV, PARTIAL, source failures, identity conflicts. Baseline collector committed; live execution awaits database read access.
- [x] Keep model-related misses tagged DEFERRED; no model change. Evidence: `MODEL_RELATED_DEFERRED` is an execution-only terminal taxonomy in `scripts/execution_hardening_forensics.py`, guarded by `tests/test_execution_hardening_forensics.py`.
Acceptance: every execution-related miss has a reproducible root-cause code.

### EH-02 — Universe discovery hardening
Owner: ChatGPT Executor
Target: Cycles 2–4
- [ ] Build source union across NSE, BSE, SEBI, Upstox IPO API, and approved specialist calendars. Reconciliation core committed in `scripts/execution_hardening_universe.py`; fail-closed provider normalization committed in `scripts/execution_hardening_universe_providers.py` with tests in `tests/test_execution_hardening_universe_providers.py`; live read-only fetch wiring and verified enumeration remain pending.
- [x] Reconcile Mainboard and SME independently. Evidence: `reconcile_universe()` plus `test_mainboard_and_sme_reconcile_independently`.
- [x] Require explicit enumeration/completeness evidence before a cycle can be COMPLETED. Evidence: healthy source requires `enumerated` and `parse_ok`; completeness tests in `tests/test_execution_hardening_universe.py`.
- [x] Treat source outage or empty parse as PARTIAL/FAILED unless independent sources prove the scoped universe. Evidence: fail-closed reconciliation and empty-universe tests.
- [x] Add per-source health and discrepancy logging. Evidence: `SourceRun.healthy`, `healthy_sources`, and per-source `discrepancies` in reconciliation result.
Acceptance: no single source can silently define an empty or incomplete universe.

### EH-03 — Canonical identity resolver
Owner: ChatGPT Executor
Target: Cycles 3–5
- [ ] Add live canonical identity map using ISIN first, then exchange identifier / Upstox IPO ID, then canonical company name + aliases. Resolver core committed in `scripts/execution_hardening_identity.py`; live/shadow ingress wiring remains pending.
- [x] Preserve historical stored names; add aliases rather than rewriting frozen rows. Evidence: fail-closed resolver preserves `input_name` and performs no DB writes; guarded by `tests/test_execution_hardening_identity.py`.
- [x] Detect duplicate/variant entities and malformed records before research persistence. Evidence: duplicate alias conflicts and unresolved variants fail closed in `scripts/execution_hardening_identity.py`, guarded by `tests/test_execution_hardening_identity.py`.
- [x] Add tests for known variants such as Hero Motors/Hero Motors Limited and Jindal Supreme/Jindal Supreme India. Evidence: `tests/test_execution_hardening_identity.py`.
Acceptance: one live IPO identity maps to one canonical research target without altering historical records.

### EH-04 — Upstox read-only provider
Owner: ChatGPT Executor
Target: Cycles 3–6
- [ ] Add provider behind feature flag `UPSTOX_ENABLED`.
- [ ] Use IPO discovery/details for structured metadata where available.
- [ ] Use read-only market/fundamental/news/market-information endpoints only where permitted and relevant.
- [ ] Never treat Upstox as sole proof for critical evidence that requires official/independent corroboration.
- [ ] Verify failure fallback: Upstox outage must not stop IPO EDGE.
- [ ] If a credential is missing or rejected, log exact dependency and continue other-source execution.
Acceptance: Upstox improves coverage but is never a single point of failure.

### EH-05 — Deterministic R1–R8 recovery ladder
Owner: ChatGPT Executor
Target: Cycles 4–7
- [ ] Encode preferred and fallback source order per block.
- [ ] Before NV, require two independent source attempts for each unresolved critical R2/R3/R4/R6/R7 block.
- [ ] Stop blocked/CAPTCHA/401/403 routes and move to legitimate alternatives; no bypass attempts.
- [ ] Persist provenance group and independence basis to prevent copied sources counting twice.
- [ ] Distinguish source fetch success from parse success and factual verification.
Acceptance: every critical NV shows exhausted, auditable recovery attempts.

### EH-06 — Research-priority routing (non-model)
Owner: ChatGPT Executor
Target: Cycles 5–7
- [ ] Add operational `RESEARCH_PRIORITY` only; it must not change score, grade or recommendation.
- [ ] Use already-verified strong partial signals to direct remaining retrieval effort to missing critical blocks.
- [ ] Add guard test proving research priority cannot bypass NV or hard blockers.
Acceptance: EDGE spends more effort on high-information unresolved IPOs without relaxing model policy.

### EH-07 — Final-day/T2 reliability
Owner: ChatGPT Executor
Target: Cycles 5–8
- [ ] Strengthen closing-day issue reconciliation.
- [ ] Validate final subscription timing after 19:00 Asia/Kolkata.
- [ ] Require verified final fields according to existing V1.1 rules.
- [ ] Never create retrospective T2; missed final-day runs remain explicit operational failures.
- [ ] Add alert/status reason for each missed or unresolved T2.
Acceptance: every eligible closing issue is either timely T2 or explicitly unresolved with cause.

### EH-08 — Observability and console diagnostics
Owner: ChatGPT Executor
Target: Cycles 6–9
- [ ] Expose per-run expected/reconciled/researched/complete/NV/PARTIAL counts.
- [ ] Show per-IPO unresolved blocks, attempted sources, conflicts, identity status, and final disposition.
- [ ] Show source health and Upstox availability separately from framework efficacy.
- [ ] Separate canonical efficacy from execution diagnostics and any replay/counterfactual analysis.
Acceptance: a PARTIAL/NV result is immediately diagnosable without reading raw receipts.

### EH-09 — Shadow replay and regression
Owner: ChatGPT Executor + GitHub Actions
Target: Cycles 8–11
- [ ] Replay frozen historical cases under the hardened execution layer without future-data leakage.
- [ ] Keep canonical historical outcomes unchanged.
- [ ] Verify same evidence => same V1.1 model output.
- [ ] Measure reductions in retrieval-driven NV/PARTIAL, identity errors, universe gaps and missed T2s.
- [ ] Flag model-related misses as DEFERRED, not fixed.
Acceptance: execution improves while model outputs remain invariant for equivalent evidence.

### EH-10 — Prospective shadow run
Owner: ChatGPT Executor
Target: after EH-00 through EH-09 pass
- [ ] Run hardening build prospectively alongside production rules.
- [ ] Persist hardening results only to isolated test/shadow storage.
- [ ] Compare coverage, completeness, timing and decision invariance.
Acceptance: unseen runs demonstrate operational improvement with zero model-rule drift.

### EH-11 — Merge readiness
Owner: ChatGPT Executor; production approval: User
Target: only after all acceptance gates pass
- [ ] Produce merge diff categorized as infrastructure / research execution / diagnostics.
- [ ] Prove zero scoring/weight/threshold/grade/NV-rule changes.
- [ ] Prove zero frozen-history mutation.
- [ ] Document rollback.
- [ ] Request explicit user approval before production merge/activation.
Acceptance: execution-only merge package ready for review.

## Hard blockers / user-action dependencies
Only raise to the user when the executor cannot proceed without account-level action. Examples:
- missing/expired Upstox read-only credential after alternative sources continue;
- connector permission required to create an isolated Neon test branch/schema;
- explicit approval to merge or activate production changes.

Current transient dependency: the connected Neon read-only SQL interface is rejecting live EH-01 baseline execution because project resolution is unavailable. This does not block repository hardening; EH-01 tooling is read-only and ready to run once database read access is restored.

## Non-negotiable acceptance gates
1. Zero model-rule changes.
2. Zero historical checkpoint/outcome mutation.
3. Same evidence => same V1.1 score, grade and decision.
4. Mainboard and SME coverage must be demonstrated before COMPLETE.
5. Upstox failure cannot stop the run.
6. Critical missing evidence remains NV after recovery exhaustion.
7. No backdated T2 and no future-data leakage.
8. Canonical efficacy remains separate from execution diagnostics/replays.
