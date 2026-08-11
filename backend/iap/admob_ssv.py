"""AdMob Server-Side Verification (SSV) — ECDSA signature verification.

Per Google AdMob docs (https://developers.google.com/admob/android/ssv):
  1. The reward callback URL ends with two trailing query params:
        &signature=<base64url>&key_id=<int>
  2. The signature is ECDSA-SHA256 over the URL query string UP TO but NOT
     INCLUDING those last two parameters.
  3. Public keys are published at:
        https://www.gstatic.com/admob/reward/verifier-keys.json
     Google rotates them periodically; consumers cache and refresh on miss.

This module is pure — no FastAPI / Mongo imports — so it can be unit-tested
against a synthetic key pair without touching the network. `server.py` wraps
it with the production kill-switch logic.
"""
from __future__ import annotations

import base64
import logging
import threading
import time
from typing import Optional

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

logger = logging.getLogger("c1.iap.admob_ssv")

VERIFIER_KEYS_URL = "https://www.gstatic.com/admob/reward/verifier-keys.json"
KEY_CACHE_TTL_SECONDS = 24 * 60 * 60  # 24h — google rotates rarely


class _KeyCache:
    """In-memory verifier-key cache. Thread-safe."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_id: dict[str, ec.EllipticCurvePublicKey] = {}
        self._fetched_at: float = 0.0
        self._last_error: Optional[str] = None

    def fresh(self) -> bool:
        return (
            bool(self._by_id) and (time.time() - self._fetched_at) < KEY_CACHE_TTL_SECONDS
        )

    def get(self, key_id: str) -> Optional[ec.EllipticCurvePublicKey]:
        return self._by_id.get(str(key_id))

    def replace_all(self, mapping: dict[str, ec.EllipticCurvePublicKey]) -> None:
        with self._lock:
            self._by_id = dict(mapping)
            self._fetched_at = time.time()
            self._last_error = None

    def note_error(self, err: str) -> None:
        with self._lock:
            self._last_error = err


_cache = _KeyCache()


def _parse_keys_document(doc: dict) -> dict[str, ec.EllipticCurvePublicKey]:
    """Turn the JSON at VERIFIER_KEYS_URL into { keyId: EC public key }."""
    keys = doc.get("keys") or []
    out: dict[str, ec.EllipticCurvePublicKey] = {}
    for entry in keys:
        try:
            kid = str(entry.get("keyId"))
            pem = entry.get("pem")
            if not pem or not kid:
                continue
            pub = serialization.load_pem_public_key(pem.encode("utf-8"))
            if not isinstance(pub, ec.EllipticCurvePublicKey):
                logger.warning("verifier key %s is not EC — skipping", kid)
                continue
            out[kid] = pub
        except Exception as e:
            logger.warning("failed to parse verifier key %r: %s", entry, e)
    return out


async def _fetch_keys_async() -> dict[str, ec.EllipticCurvePublicKey]:
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(VERIFIER_KEYS_URL)
    if r.status_code != 200:
        raise RuntimeError(f"verifier-keys HTTP {r.status_code}")
    return _parse_keys_document(r.json())


async def refresh_keys_if_needed(force: bool = False) -> bool:
    """Ensure the key cache is fresh. Returns True if usable keys are loaded.

    Fail-closed: on any fetch/parse error we do NOT clobber the existing cache,
    so a transient outage doesn't break verification if we already had keys.
    """
    if not force and _cache.fresh():
        return True
    try:
        mapping = await _fetch_keys_async()
        if not mapping:
            _cache.note_error("verifier-keys response contained no usable keys")
            return _cache.fresh()
        _cache.replace_all(mapping)
        logger.info("AdMob verifier keys refreshed: %d key(s)", len(mapping))
        return True
    except Exception as e:
        logger.warning("failed to fetch AdMob verifier keys: %s", e)
        _cache.note_error(str(e))
        return _cache.fresh()  # can still verify with previously cached keys


def _b64url_decode(sig: str) -> bytes:
    """Decode base64url (with or without padding) → raw bytes."""
    s = sig.replace("-", "+").replace("_", "/")
    pad = (-len(s)) % 4
    return base64.b64decode(s + ("=" * pad))


def _signed_content_from_query(raw_query: str) -> Optional[str]:
    """Return the substring of `raw_query` before the trailing
    `signature=...&key_id=...` parameters — that's what Google signed.

    Per AdMob spec these are always the last two params, in that order.
    """
    if not raw_query:
        return None
    # Prefer the canonical `?...&signature=...&key_id=...` order; fall back to
    # locating just `&signature=` if the sender is more lenient.
    i = raw_query.rfind("&signature=")
    if i == -1:
        # Signature might be the first (and only) param — rare but possible.
        if raw_query.startswith("signature="):
            return ""
        return None
    return raw_query[:i]


async def verify_ssv_request(
    raw_query: str, signature_b64: str, key_id: str
) -> tuple[bool, str]:
    """Verify an AdMob SSV callback signature.

    Returns (ok, error_reason). `ok` is True only for a fully-verified signature
    against Google's current or previously-cached public keys.
    """
    if not signature_b64 or not key_id:
        return False, "missing signature/key_id"

    signed_content = _signed_content_from_query(raw_query)
    if signed_content is None:
        return False, "cannot locate signed content in query"

    # Load or refresh the verifier keys.
    if not _cache.fresh() and not await refresh_keys_if_needed():
        return False, "verifier keys unavailable"

    pub = _cache.get(str(key_id))
    if pub is None:
        # Maybe the caller is using a key that rotated since our last fetch.
        await refresh_keys_if_needed(force=True)
        pub = _cache.get(str(key_id))
        if pub is None:
            return False, f"unknown key_id {key_id}"

    try:
        sig = _b64url_decode(signature_b64)
    except Exception as e:
        return False, f"signature b64 decode failed: {e}"

    try:
        pub.verify(sig, signed_content.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
        return True, ""
    except InvalidSignature:
        return False, "invalid signature"
    except Exception as e:
        return False, f"verify raised: {e}"


# ---------------------------------------------------------------------------
# Test hooks — used by unit tests to install a synthetic verifier key without
# needing network access. NEVER call these from production code.
# ---------------------------------------------------------------------------
def _test_install_key(key_id: str, pub: ec.EllipticCurvePublicKey) -> None:
    _cache.replace_all({str(key_id): pub})


def _test_reset_cache() -> None:
    _cache.replace_all({})
    _cache._fetched_at = 0.0  # noqa: SLF001
