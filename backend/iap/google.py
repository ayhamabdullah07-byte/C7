"""Google Play Developer API + RTDN (Real-Time Developer Notifications) integration.

Phase 1: Skeleton only — function signatures with NotImplementedError bodies.
Phase 3 will wire:
  - androidpublisher.purchases.subscriptionsv2.get for canonical state
  - purchases.subscriptions.acknowledge (3-day acknowledge window)
  - Pub/Sub push JWT verification + message dedupe on messageId
  - Notification routing (SUBSCRIPTION_RENEWED / CANCELED / ON_HOLD /
    IN_GRACE_PERIOD / PAUSED / REVOKED / EXPIRED / voidedPurchase /
    tolerant handling of future types).
"""
from __future__ import annotations


async def verify_purchase(
    purchase_token: str, subscription_id: str, base_plan_id: str
) -> dict:
    """Verify a client-supplied purchase token and return canonical Google state.

    Phase 3 implementation:
      1. Call subscriptionsv2.get(packageName, token) via service-account OAuth.
      2. Assert packageName matches and subscriptionState in {ACTIVE, IN_GRACE_PERIOD}.
      3. Extract lineItems[0], expiryTime, autoRenewingPlan, offerDetails.
      4. Acknowledge if not already acknowledged (3-day rule).
      5. Return normalized dict for `subscriptions` upsert.
    """
    raise NotImplementedError("Google purchase verification arrives in Phase 3.")


async def refetch_subscription(purchase_token: str) -> dict:
    """Fetch canonical subscription state from Google by purchase token."""
    raise NotImplementedError("Play Developer API client arrives in Phase 3.")


async def handle_rtdn(pubsub_message: dict) -> dict:
    """Handle a Real-Time Developer Notification Pub/Sub push.

    Phase 3 implementation:
      1. Verify Pub/Sub JWT signature + audience.
      2. Base64-decode message.data → notification body.
      3. Dedupe on messageId.
      4. Route by notification type; unknown types → iap_events with
         processing_note="unknown_type" and ack HTTP 200.
    """
    raise NotImplementedError("RTDN handling arrives in Phase 3.")
