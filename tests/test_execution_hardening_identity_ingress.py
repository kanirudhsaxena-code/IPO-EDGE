import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module

identity = load("eh_identity", "scripts/execution_hardening_identity.py")
ingress = load("eh_identity_ingress", "scripts/execution_hardening_identity_ingress.py")


def config(master=True, feature=True):
    return {
        "shadow_only": True,
        "production_writes": False,
        "rollback": {"master_enabled": master},
        "features": {"identity_resolver": feature},
        "invariants": {"allow_model_changes": False},
    }


def resolver():
    return identity.IdentityResolver([
        identity.CanonicalIPO("hero-motors", "Hero Motors Limited", isin="INEHERO1", aliases=("Hero Motors",)),
    ])


def test_shadow_ingress_is_off_when_master_switch_is_off():
    out = ingress.resolve_shadow_identity(config(master=False), resolver(), identity.IdentityInput(name="Hero Motors"))
    assert out.status == "BYPASSED"
    assert out.reason == "HARDENING_MASTER_DISABLED"


def test_shadow_ingress_is_off_when_identity_feature_is_off():
    out = ingress.resolve_shadow_identity(config(feature=False), resolver(), identity.IdentityInput(name="Hero Motors"))
    assert out.status == "BYPASSED"
    assert out.reason == "IDENTITY_RESOLVER_DISABLED"


def test_shadow_ingress_rejects_production_write_configuration():
    cfg = config()
    cfg["production_writes"] = True
    out = ingress.resolve_shadow_identity(cfg, resolver(), identity.IdentityInput(name="Hero Motors"))
    assert out.status == "BYPASSED"
    assert out.reason == "PRODUCTION_WRITES_MUST_BE_DISABLED"


def test_shadow_ingress_resolves_without_mutating_input():
    incoming = identity.IdentityInput(name="Hero Motors")
    out = ingress.resolve_shadow_identity(config(), resolver(), incoming)
    assert out.status == "RESOLVED"
    assert out.canonical_id == "hero-motors"
    assert incoming.name == "Hero Motors"


def test_ambiguous_map_fails_closed_before_resolution():
    r = identity.IdentityResolver([
        identity.CanonicalIPO("a", "Alpha Limited", aliases=("Shared",)),
        identity.CanonicalIPO("b", "Beta Limited", aliases=("Shared",)),
    ])
    out = ingress.resolve_shadow_identity(config(), r, identity.IdentityInput(name="Shared"))
    assert out.status == "CONFLICT"
    assert out.reason == "CANONICAL_MAP_AMBIGUOUS"
