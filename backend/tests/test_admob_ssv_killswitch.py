"""Production kill-switch tests for the AdMob SSV verifier.

These tests verify the *policy* semantics of `_verify_admob_signature`:
  Prod (SSV enforce ON, dev bypass OFF)  → refuse (until ECDSA is wired)
  Dev  (SSV enforce OFF, dev bypass ON)  → accept
  Locked (both OFF)                       → refuse (safe default)

They monkey-patch the module-level flags so the tests are hermetic; no env
mutation required and no dependency on the running backend process.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

# Import server via a sys.path insert so pytest picks up the same module the
# app runs from.
BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


@pytest.fixture
def srv():
    """Return the server module and restore its flag state after each test."""
    mod = importlib.import_module("server")
    orig_enforce = mod.ADMOB_SSV_ENFORCE
    orig_dev = mod.ADMOB_ALLOW_DEV_REWARD
    try:
        yield mod
    finally:
        mod.ADMOB_SSV_ENFORCE = orig_enforce
        mod.ADMOB_ALLOW_DEV_REWARD = orig_dev


def test_production_defaults_refuse_when_verifier_not_wired(srv):
    """SSV enforce=True with no ECDSA verifier ⇒ fail-closed (refuse)."""
    srv.ADMOB_SSV_ENFORCE = True
    srv.ADMOB_ALLOW_DEV_REWARD = False
    assert srv._verify_admob_signature("qs=1", "sig", "1") is False


def test_dev_bypass_accepts_synthetic_signature(srv):
    """Dev builds may explicitly opt-in to the synthetic bypass."""
    srv.ADMOB_SSV_ENFORCE = False
    srv.ADMOB_ALLOW_DEV_REWARD = True
    assert srv._verify_admob_signature("qs=1", "dev", "dev") is True


def test_locked_default_refuses(srv):
    """Both flags off (a mis-configured deployment) refuses rewards. Safe default."""
    srv.ADMOB_SSV_ENFORCE = False
    srv.ADMOB_ALLOW_DEV_REWARD = False
    assert srv._verify_admob_signature("qs=1", "sig", "1") is False


def test_prod_wins_over_dev_flag(srv):
    """If someone accidentally enables both in prod, enforce still fail-closes
    because ECDSA verification isn't wired yet."""
    srv.ADMOB_SSV_ENFORCE = True
    srv.ADMOB_ALLOW_DEV_REWARD = True
    assert srv._verify_admob_signature("qs=1", "dev", "dev") is False
