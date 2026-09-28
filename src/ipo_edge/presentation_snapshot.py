"""P0-11 immutable user-facing presentation snapshot contract for IPO EDGE.

Presentation/persistence semantics only. No grading, scoring, checkpoint selection,
efficacy, learning adoption or trading behavior is changed. Production persistence
remains disabled until the schema migration is validated on a temporary Neon
branch and explicitly approved for production application.
"""
from __future__ import annotations

import hashlib
import json
import math
import struct
from decimal import Decimal
from typing import Any, Mapping, Sequence

PRESENTATION_CONTRACT_VERSION = "P0_11_PRESENTATION_V1"
ENGINE = "IPO_EDGE"
MAX_SAFE_INTEGER = 2**53 - 1
REQUIRED_SECTIONS = (
    "EFFICACY_ASSESSMENT",
    "MISSED_OPPORTUNITIES",
    "CONTINUOUS_LEARNINGS",
    "CURRENT_OPPORTUNITIES",
)


def _number_to_f64(value: int | float | Decimal) -> float:
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("PRESENTATION_NON_FINITE_NUMBER")
        numeric = float(value)
    else:
        numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError("PRESENTATION_NON_FINITE_NUMBER")
    if numeric.is_integer() and abs(numeric) > MAX_SAFE_INTEGER:
        raise ValueError("PRESENTATION_UNSAFE_INTEGER_USE_STRING")
    return numeric


def _semantic_node(value: Any) -> Any:
    if value is None:
        return ["null"]
    if isinstance(value, bool):
        return ["boolean", value]
    if isinstance(value, str):
        return ["string", value]
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return ["number_f64", struct.pack(">d", _number_to_f64(value)).hex()]
    if isinstance(value, list):
        return ["array", [_semantic_node(item) for item in value]]
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("PRESENTATION_NON_STRING_OBJECT_KEY")
        return ["object", [[key, _semantic_node(value[key])] for key in sorted(value)]]
    raise ValueError("PRESENTATION_NON_JSON_VALUE")


def semantic_presentation_hash(value: Any) -> str:
    semantic = json.dumps(_semantic_node(value), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(semantic.encode("utf-8")).hexdigest()


def _validate_sections(sections: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(sections, Sequence) or isinstance(sections, (str, bytes)) or not sections:
        raise ValueError("PRESENTATION_MISSING_SECTIONS")
    normalized = [dict(section) for section in sections]
    names = tuple(section.get("name") for section in normalized)
    if names != REQUIRED_SECTIONS:
        raise ValueError("PRESENTATION_IPO_SECTION_ORDER_MISMATCH")
    return normalized


def build_presentation_snapshot(
    *,
    run_id: str | int,
    ipo_id: str | int,
    checkpoint_id: str | int,
    governance_state: str,
    sections: Sequence[Mapping[str, Any]],
    source_payload_hash: str,
) -> dict[str, Any]:
    if not str(run_id).strip():
        raise ValueError("PRESENTATION_MISSING_RUN_ID")
    if not str(ipo_id).strip():
        raise ValueError("PRESENTATION_MISSING_RESULT_ID")
    if not str(checkpoint_id).strip():
        raise ValueError("PRESENTATION_MISSING_CHECKPOINT_ID")
    if not str(governance_state).strip():
        raise ValueError("PRESENTATION_MISSING_GOVERNANCE_STATE")
    if not str(source_payload_hash).strip():
        raise ValueError("PRESENTATION_MISSING_SOURCE_HASH")
    normalized_sections = _validate_sections(sections)
    basis = {
        "presentation_contract_version": PRESENTATION_CONTRACT_VERSION,
        "engine": ENGINE,
        "identity": {
            "run_id": str(run_id),
            "result_id": str(ipo_id),
            "checkpoint_id": str(checkpoint_id),
        },
        "governance_state": str(governance_state),
        "sections": normalized_sections,
        "source_payload_hash": str(source_payload_hash),
    }
    return {**basis, "presentation_hash": semantic_presentation_hash(basis)}


def assert_presentation_snapshot(snapshot: Mapping[str, Any]) -> None:
    if snapshot.get("presentation_contract_version") != PRESENTATION_CONTRACT_VERSION:
        raise ValueError("PRESENTATION_CONTRACT_VERSION_UNSUPPORTED")
    if snapshot.get("engine") != ENGINE:
        raise ValueError("PRESENTATION_ENGINE_MISMATCH")
    presentation_hash = snapshot.get("presentation_hash")
    if not isinstance(presentation_hash, str):
        raise ValueError("PRESENTATION_HASH_MISSING")
    basis = {key: value for key, value in snapshot.items() if key != "presentation_hash"}
    if semantic_presentation_hash(basis) != presentation_hash:
        raise ValueError("PRESENTATION_HASH_MISMATCH")
    _validate_sections(snapshot.get("sections", []))
