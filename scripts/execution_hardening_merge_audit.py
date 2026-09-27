#!/usr/bin/env python3
"""Fail-closed merge-readiness audit for IPO EDGE V1.1 execution hardening.

This utility is deliberately policy-blind: it does not modify production, recompute
scores, or write historical data. It classifies a supplied git diff and rejects any
change touching frozen model/history surfaces unless explicitly reviewed outside this
tool. It is additive hardening infrastructure only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path

FROZEN_PREFIXES = (
    "config/framework_v1.1.json",
    "migrations/",
)
FROZEN_TOKENS = (
    "score", "weight", "grade", "threshold", "nv_gate", "recommendation",
    "checkpoint", "outcome", "t2", "historical",
)
ALLOWED_HARDENING_PREFIXES = (
    "scripts/execution_hardening_",
    "tests/test_execution_hardening_",
    "docs/EXECUTION_HARDENING",
    "config/execution_hardening_",
)

@dataclass(frozen=True)
class Audit:
    base: str
    head: str
    files: tuple[str, ...]
    execution_only: tuple[str, ...]
    suspicious: tuple[str, ...]
    frozen_surface_touched: tuple[str, ...]
    pass_fail_closed: bool


def changed_files(base: str, head: str) -> list[str]:
    out = subprocess.check_output(["git", "diff", "--name-only", f"{base}...{head}"], text=True)
    return [x.strip() for x in out.splitlines() if x.strip()]


def classify(files: list[str], base: str, head: str) -> Audit:
    execution_only, suspicious, frozen = [], [], []
    for path in files:
        low = path.lower()
        if path.startswith(FROZEN_PREFIXES) or any(tok in low for tok in FROZEN_TOKENS):
            frozen.append(path)
        if path.startswith(ALLOWED_HARDENING_PREFIXES):
            execution_only.append(path)
        else:
            suspicious.append(path)
    # Fail closed: merge readiness cannot pass with any unclassified or frozen-surface file.
    ok = not suspicious and not frozen
    return Audit(base, head, tuple(files), tuple(execution_only), tuple(suspicious), tuple(frozen), ok)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="main")
    p.add_argument("--head", default="HEAD")
    p.add_argument("--output")
    a = p.parse_args()
    audit = classify(changed_files(a.base, a.head), a.base, a.head)
    payload = json.dumps(asdict(audit), indent=2, sort_keys=True)
    if a.output:
        Path(a.output).write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if audit.pass_fail_closed else 2

if __name__ == "__main__":
    raise SystemExit(main())
