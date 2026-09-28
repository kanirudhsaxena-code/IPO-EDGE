"""EH-06 operational research-priority routing.

This module only orders unresolved research work. It does not calculate or
modify IPO EDGE scores, grades, thresholds, hard blockers, NV disposition or
recommendations. Strong partial signals are inputs already verified elsewhere;
this layer never creates or reinterprets them.
"""
from dataclasses import dataclass
from typing import Iterable, Mapping

CRITICAL_BLOCKS = frozenset({"R2", "R3", "R4", "R6", "R7"})
ALL_BLOCKS = tuple(f"R{i}" for i in range(1, 9))


@dataclass(frozen=True)
class ResearchTask:
    block: str
    priority: int
    reason: str


def research_priority(
    unresolved_blocks: Iterable[str],
    *,
    verified_strong_partial_signals: Mapping[str, bool] | None = None,
) -> tuple[ResearchTask, ...]:
    """Order missing research blocks without changing model policy.

    Critical unresolved blocks always precede non-critical blocks. When the
    caller already has verified strong partial signals, the execution layer
    increases retrieval urgency for the remaining critical gaps only; it does
    not infer a model outcome from those signals.
    """
    unresolved = []
    seen = set()
    for block in unresolved_blocks:
        if block not in ALL_BLOCKS:
            raise ValueError(f"unknown research block: {block}")
        if block not in seen:
            unresolved.append(block)
            seen.add(block)

    strong = verified_strong_partial_signals or {}
    strong_count = sum(1 for value in strong.values() if value is True)

    tasks = []
    for block in unresolved:
        critical = block in CRITICAL_BLOCKS
        # Priority is execution-only: lower number means fetch earlier.
        if critical and strong_count:
            priority = 0
            reason = "missing critical block with verified strong partial signals elsewhere"
        elif critical:
            priority = 1
            reason = "missing critical block"
        else:
            priority = 2
            reason = "missing non-critical block"
        tasks.append(ResearchTask(block=block, priority=priority, reason=reason))

    block_order = {block: index for index, block in enumerate(ALL_BLOCKS)}
    return tuple(sorted(tasks, key=lambda task: (task.priority, block_order[task.block])))


def preserve_disposition(disposition: str, *, hard_blocker: str | None = None) -> tuple[str, str | None]:
    """Explicit guard: routing cannot alter disposition or hard blocker."""
    return disposition, hard_blocker


def research_priority_audit(
    unresolved_blocks: Iterable[str],
    *,
    verified_strong_partial_signals: Mapping[str, bool] | None = None,
    disposition: str,
    hard_blocker: str | None = None,
) -> dict[str, object]:
    tasks = research_priority(
        unresolved_blocks,
        verified_strong_partial_signals=verified_strong_partial_signals,
    )
    preserved_disposition, preserved_blocker = preserve_disposition(
        disposition,
        hard_blocker=hard_blocker,
    )
    return {
        "research_priority": [
            {"block": task.block, "priority": task.priority, "reason": task.reason}
            for task in tasks
        ],
        "disposition": preserved_disposition,
        "hard_blocker": preserved_blocker,
        "model_policy_changed": False,
    }
