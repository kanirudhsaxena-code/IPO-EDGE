import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

spec = importlib.util.spec_from_file_location(
    "execution_hardening_identity_feed", SCRIPTS / "execution_hardening_identity_feed.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

build_canonical_map = module.build_canonical_map
build_shadow_resolver = module.build_shadow_resolver


def test_feed_merges_explicit_provider_identifiers_and_aliases():
    rows = [
        {"canonical_id": "hero-motors", "canonical_name": "Hero Motors Limited",
         "isin": "INE000H01001", "exchange_id": "NSE:HERO", "aliases": ["Hero Motors"]},
        {"canonical_id": "hero-motors", "canonical_name": "Hero Motors Limited",
         "upstox_id": "UP-HERO", "aliases": ["HERO MOTORS LIMITED"]},
    ]
    records = build_canonical_map(rows)
    assert len(records) == 1
    record = records[0]
    assert record.canonical_name == "Hero Motors Limited"
    assert record.isin == "INE000H01001"
    assert record.exchange_ids == ("NSE:HERO",)
    assert record.upstox_ids == ("UP-HERO",)
    assert "Hero Motors" in record.aliases


def test_feed_fails_closed_on_missing_explicit_canonical_identity():
    try:
        build_canonical_map([{"name": "Unknown IPO", "isin": "INE000X01001"}])
    except ValueError as exc:
        assert "missing canonical_id/canonical_name" in str(exc)
    else:
        raise AssertionError("feed must fail closed")


def test_feed_fails_closed_on_conflicting_canonical_name_or_isin():
    for rows in (
        [
            {"canonical_id": "x", "canonical_name": "X Limited"},
            {"canonical_id": "x", "canonical_name": "Different Limited"},
        ],
        [
            {"canonical_id": "x", "canonical_name": "X Limited", "isin": "INE001"},
            {"canonical_id": "x", "canonical_name": "X Limited", "isin": "INE002"},
        ],
    ):
        try:
            build_canonical_map(rows)
        except ValueError:
            pass
        else:
            raise AssertionError("conflicting feed must fail closed")


def test_feed_rejects_cross_entity_alias_ambiguity_before_ingress():
    rows = [
        {"canonical_id": "a", "canonical_name": "A Limited", "aliases": ["Shared"]},
        {"canonical_id": "b", "canonical_name": "B Limited", "aliases": ["Shared"]},
    ]
    try:
        build_shadow_resolver(rows)
    except ValueError as exc:
        assert "ambiguous identity keys" in str(exc)
    else:
        raise AssertionError("ambiguous feed must fail closed")


def test_feed_is_read_only_data_transform():
    rows = [{"canonical_id": "jindal-supreme", "canonical_name": "Jindal Supreme India",
             "aliases": ["Jindal Supreme"]}]
    original = [dict(rows[0])]
    resolver = build_shadow_resolver(rows)
    assert rows == original
    assert resolver.duplicate_keys() == {}
