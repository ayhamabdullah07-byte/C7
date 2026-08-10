"""Apple App Store Server API + Notifications V2 integration.

Phase 1: Skeleton only — function signatures with NotImplementedError bodies.
Phase 2 will wire:
  - JWS transaction verification against Apple's x5c cert chain
  - GET /inApps/v1/subscriptions/{originalTransactionId}
  - Server-side notification handler (DID_RENEW / EXPIRED / REFUND / REVOKE /
    GRACE_PERIOD_EXPIRED / DID_FAIL_TO_RENEW / SUBSCRIBED / DID_CHANGE_RENEWAL_STATUS
    plus tolerant handling of unknown types).
"""
from __future__ import annotations


async def verify_transaction(jws_representation: str, transaction_id: str) -> dict:
    """Verify a client-supplied JWS transaction and return canonical Apple state.

    Phase 2 implementation:
      1. Verify JWS signature against Apple root cert (x5c chain).
      2. Extract originalTransactionId + productId + environment.
      3. Call GET /inApps/v1/subscriptions/{originalTransactionId} for canonical state.
      4. Return a normalized dict for upsert into the `subscriptions` collection.
    """
    raise NotImplementedError("Apple JWS verification arrives in Phase 2.")


async def refetch_subscription(original_transaction_id: str) -> dict:
    """Fetch canonical subscription state from Apple by originalTransactionId."""
    raise NotImplementedError("App Store Server API client arrives in Phase 2.")


async def handle_notification(signed_payload: str) -> dict:
    """Handle an App Store Server Notification V2 payload.

    Phase 2 implementation:
      1. Verify JWS signature.
      2. Extract notificationType + subtype + signedTransactionInfo + signedRenewalInfo.
      3. Dedupe on notificationUUID.
      4. Route to the appropriate subscription update; on unknown types, log to
         iap_events with processing_note="unknown_type" and ack HTTP 200.
    """
    raise NotImplementedError("Apple notification handling arrives in Phase 2.")
