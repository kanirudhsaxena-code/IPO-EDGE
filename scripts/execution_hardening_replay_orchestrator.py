"""Fail-closed orchestration for IPO EDGE V1.1 historical shadow replay.

Consumes explicit frozen-case and shadow-result JSON only. It never queries or
writes production state, never recomputes model rules, and never permits replay
evidence later than the canonical checkpoint.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from execution_hardening_shadow_replay import FrozenCase, ShadowResult, validate_replay_batch, measure_execution_deltas


def _dt(value: str) -> datetime:
    value = value.replace("Z", "+00:00")
    return datetime.fromisoformat(value)


def _fingerprint(rows: list[dict[str, Any]]) -> str:
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def run(payload: dict[str, Any]) -> dict[str, Any]:
    cases = payload.get("frozen_cases")
    shadows = payload.get("shadow_results")
    if not isinstance(cases, list) or not isinstance(shadows, list):
        raise ValueError("explicit frozen_cases and shadow_results lists required")
    if len(cases) != len(shadows):
        raise ValueError("replay population mismatch")

    pairs = []
    before = []
    after = []
    for c, s in zip(cases, shadows):
        case = FrozenCase(
            case_id=str(c["case_id"]), checkpoint_at=_dt(c["checkpoint_at"]),
            evidence_as_of=_dt(c["evidence_as_of"]), evidence_fingerprint=str(c["evidence_fingerprint"]),
            score=c["score"], grade=c["grade"], decision=c["decision"],
            outcome_fingerprint=str(c["outcome_fingerprint"]),
        )
        shadow = ShadowResult(
            case_id=str(s["case_id"]), evidence_as_of=_dt(s["evidence_as_of"]),
            evidence_fingerprint=str(s["evidence_fingerprint"]), score=s["score"],
            grade=s["grade"], decision=s["decision"],
            canonical_outcome_fingerprint=str(s["canonical_outcome_fingerprint"]),
            retrieval_nv=bool(s.get("retrieval_nv", False)), partial=bool(s.get("partial", False)),
            identity_error=bool(s.get("identity_error", False)), universe_gap=bool(s.get("universe_gap", False)),
            missed_t2=bool(s.get("missed_t2", False)), model_related_miss=bool(s.get("model_related_miss", False)),
        )
        pairs.append((case, shadow))
        before.append({k: bool(c.get(k, False)) for k in ("retrieval_nv", "partial", "identity_error", "universe_gap", "missed_t2")})
        after.append({k: bool(s.get(k, False)) for k in ("retrieval_nv", "partial", "identity_error", "universe_gap", "missed_t2")})

    validation = validate_replay_batch(pairs)
    return {
        "kind": "EXECUTION_HARDENING_SHADOW_REPLAY",
        "canonical_population_fingerprint": _fingerprint(cases),
        "shadow_population_fingerprint": _fingerprint(shadows),
        "population": len(pairs),
        "validation": validation,
        "execution_deltas": measure_execution_deltas(before, after),
        "canonical_history_mutated": False,
        "model_rules_changed": False,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("input", type=Path)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    result = run(json.loads(args.input.read_text()))
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(text + "\n")
    else:
        print(text)


if __name__ == "__main__":
    main()
