import importlib.util
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "scripts" / "execution_hardening_identity.py"
spec = importlib.util.spec_from_file_location("execution_hardening_identity", PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)
CanonicalIPO = module.CanonicalIPO
IdentityInput = module.IdentityInput
IdentityResolver = module.IdentityResolver


def resolver():
    return IdentityResolver([
        CanonicalIPO("hero-motors", "Hero Motors Limited", isin="INEHERO1", exchange_ids=("NSE:HERO",), aliases=("Hero Motors",)),
        CanonicalIPO("jindal-supreme", "Jindal Supreme India Limited", isin="INEJIND1", upstox_ids=("UP-JINDAL",), aliases=("Jindal Supreme", "Jindal Supreme India")),
    ])


def test_isin_has_precedence_over_conflicting_name():
    result = resolver().resolve(IdentityInput(isin="INEHERO1", name="Jindal Supreme"))
    assert result.status == "RESOLVED"
    assert result.canonical_id == "hero-motors"
    assert result.matched_by == "isin"


def test_exchange_then_upstox_identifiers_resolve():
    assert resolver().resolve(IdentityInput(exchange_id="NSE:HERO")).canonical_id == "hero-motors"
    assert resolver().resolve(IdentityInput(upstox_id="UP-JINDAL")).canonical_id == "jindal-supreme"


def test_known_name_variants_are_explicit_aliases():
    assert resolver().resolve(IdentityInput(name="Hero Motors")).canonical_id == "hero-motors"
    assert resolver().resolve(IdentityInput(name="Hero Motors Limited")).canonical_id == "hero-motors"
    assert resolver().resolve(IdentityInput(name="Jindal Supreme")).canonical_id == "jindal-supreme"
    assert resolver().resolve(IdentityInput(name="Jindal Supreme India")).canonical_id == "jindal-supreme"


def test_unknown_name_does_not_fuzzy_match():
    result = resolver().resolve(IdentityInput(name="Hero Motorz"))
    assert result.status == "UNRESOLVED"


def test_duplicate_alias_fails_closed_before_persistence():
    r = IdentityResolver([
        CanonicalIPO("a", "Alpha Limited", aliases=("Shared IPO",)),
        CanonicalIPO("b", "Beta Limited", aliases=("Shared IPO",)),
    ])
    assert r.resolve(IdentityInput(name="Shared IPO")).status == "CONFLICT"
    assert r.duplicate_keys()["name:SHARED IPO"] == ("a", "b")


def test_input_name_is_not_mutated_or_rewritten():
    original = IdentityInput(name="Hero Motors")
    resolver().resolve(original)
    assert original.name == "Hero Motors"
