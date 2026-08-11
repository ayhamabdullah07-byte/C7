/**
 * Google Play Billing wrapper — web / Expo Go safe by default.
 *
 * The real Play Billing bindings live in `./google-billing.native.ts` and are
 * loaded ONLY when the Google Mobile Ads / IAP native modules can be resolved.
 * This ambient module always exists so the rest of the app can import it
 * without breaking Metro on web builds.
 *
 * Public surface:
 *   billingAvailable()                                   → boolean
 *   initBilling()                                        → Promise<boolean>
 *   fetchSubscriptions(skus: string[])                   → Promise<SubProduct[]>
 *   requestSubscriptionPurchase(sku, basePlanId?)        → Promise<PurchaseResult>
 *
 * PurchaseResult surfaces the outcome of the native purchase sheet AND the
 * server-side verification response so the caller can update auth state.
 */
import Constants from 'expo-constants';
import { Platform } from 'react-native';
import { api } from './api';

export type SubProduct = {
  id: string;
  title: string;
  description: string;
  displayPrice: string;
  currency?: string;
  basePlans: Array<{
    basePlanId: string;
    offerToken: string;
    priceAmountMicros?: string;
    priceCurrencyCode?: string;
    formattedPrice?: string;
    billingPeriod?: string; // P1M | P1Y
  }>;
};

export type PurchaseResult =
  | { status: 'success'; plan: 'premium' | 'plus'; period?: 'P1M' | 'P1Y' }
  | { status: 'user_cancelled' }
  | { status: 'unavailable'; reason: string }
  | { status: 'failed'; error: string };

// ---------------------------------------------------------------------------
// Native module detection — lazy + Metro-safe
// ---------------------------------------------------------------------------
type NativeIAP = typeof import('react-native-iap');
let iap: NativeIAP | null = null;
let checked = false;
let initPromise: Promise<boolean> | null = null;

function loadNative(): NativeIAP | null {
  if (checked) return iap;
  checked = true;
  try {
    const appOwnership = (Constants as any).appOwnership;
    if (appOwnership === 'expo' || Platform.OS === 'web' || Platform.OS !== 'android') {
      // Play Billing is Android-only. iOS uses Apple StoreKit (separate module).
      return null;
    }
    const mod = require('react-native-iap') as NativeIAP;
    if (!mod || typeof (mod as any).initConnection !== 'function') return null;
    iap = mod;
    return mod;
  } catch (e) {
    console.warn('[billing] react-native-iap unavailable', e);
    return null;
  }
}

export function billingAvailable(): boolean {
  return loadNative() !== null;
}

export async function initBilling(): Promise<boolean> {
  const mod = loadNative();
  if (!mod) return false;
  if (initPromise) return initPromise;
  initPromise = (async () => {
    try {
      await (mod as any).initConnection();
      return true;
    } catch (e) {
      console.warn('[billing] initConnection failed', e);
      return false;
    }
  })();
  return initPromise;
}

// ---------------------------------------------------------------------------
// Fetch subscription products
// ---------------------------------------------------------------------------
export async function fetchSubscriptions(skus: string[]): Promise<SubProduct[]> {
  const mod = loadNative();
  if (!mod) return [];
  await initBilling();
  try {
    // react-native-iap v16 API — getSubscriptions returns an array of items.
    const raw: any[] = await (mod as any).getSubscriptions({ skus });
    return raw.map((p: any) => ({
      id: p.productId || p.id,
      title: p.title || '',
      description: p.description || '',
      displayPrice: p.localizedPrice || p.price || '',
      currency: p.currency,
      basePlans: (p.subscriptionOfferDetails || p.subscriptionOfferDetailsAndroid || []).map(
        (o: any) => ({
          basePlanId: o.basePlanId,
          offerToken: o.offerToken,
          formattedPrice: o.pricingPhases?.pricingPhaseList?.[0]?.formattedPrice,
          priceAmountMicros: o.pricingPhases?.pricingPhaseList?.[0]?.priceAmountMicros,
          priceCurrencyCode: o.pricingPhases?.pricingPhaseList?.[0]?.priceCurrencyCode,
          billingPeriod: o.pricingPhases?.pricingPhaseList?.[0]?.billingPeriod,
        }),
      ),
    }));
  } catch (e) {
    console.warn('[billing] fetchSubscriptions failed', e);
    return [];
  }
}

// ---------------------------------------------------------------------------
// Purchase flow — launches Google Play sheet, then verifies with backend
// ---------------------------------------------------------------------------
const PACKAGE_NAME = 'com.ayhamabdullah.c1';

export async function requestSubscriptionPurchase(
  sku: string,
  basePlanId?: string,
): Promise<PurchaseResult> {
  const mod = loadNative();
  if (!mod) {
    return {
      status: 'unavailable',
      reason:
        Platform.OS === 'ios'
          ? 'Apple In-App Purchase support is coming next. Google Play purchases are Android-only.'
          : 'Google Play Billing is only available in a production/internal-testing Android build (not Expo Go).',
    };
  }
  await initBilling();
  try {
    // 1. Load products & find the right offer token
    const products = await fetchSubscriptions([sku]);
    const product = products.find((p) => p.id === sku);
    if (!product) {
      return { status: 'failed', error: `Product ${sku} not configured in Google Play.` };
    }
    const offer = basePlanId
      ? product.basePlans.find((b) => b.basePlanId === basePlanId)
      : product.basePlans[0];
    if (!offer?.offerToken) {
      return {
        status: 'failed',
        error: `No active base plan (${basePlanId || 'default'}) for ${sku} in Google Play.`,
      };
    }

    // 2. Launch native purchase sheet
    const M: any = mod;
    // v16 signature accepts { request: {...}, type: 'subs' }
    const purchase: any = await M.requestSubscription({
      sku,
      subscriptionOffers: [{ sku, offerToken: offer.offerToken }],
      // subscriptionOffersAndroid is the alt name in some versions
      subscriptionOffersAndroid: [{ sku, offerToken: offer.offerToken }],
    });

    // In some flows purchase comes as an array; normalize.
    const p = Array.isArray(purchase) ? purchase[0] : purchase;
    const purchaseToken: string | undefined =
      p?.purchaseToken || p?.purchaseTokenAndroid || p?.transactionReceipt;
    if (!purchaseToken) {
      return { status: 'failed', error: 'No purchase token returned by Google Play.' };
    }

    // 3. Verify server-side (source of truth). Server upserts subscription
    //    doc + updates user.plan. We only mark the native tx as finished
    //    AFTER server acknowledges — otherwise we can lose entitlement.
    try {
      const verify = await api.verifyGoogle(
        purchaseToken,
        sku,
        basePlanId || 'monthly',
        sku,
      );
      // Acknowledge on the native side so Google doesn't auto-refund.
      try {
        if (typeof M.finishTransaction === 'function') {
          await M.finishTransaction({ purchase: p, isConsumable: false });
        } else if (typeof M.acknowledgePurchaseAndroid === 'function') {
          await M.acknowledgePurchaseAndroid({ token: purchaseToken });
        }
      } catch (ackErr) {
        console.warn('[billing] finishTransaction/ack failed', ackErr);
      }
      return {
        status: 'success',
        plan: verify?.plan || (sku === 'c1_premium' ? 'premium' : 'plus'),
        period: verify?.period,
      };
    } catch (e: any) {
      return { status: 'failed', error: e?.message || 'Verification failed.' };
    }
  } catch (e: any) {
    const msg = String(e?.message || e);
    if (/cancel/i.test(msg) || e?.code === 'E_USER_CANCELLED') {
      return { status: 'user_cancelled' };
    }
    return { status: 'failed', error: msg };
  }
}

// ---------------------------------------------------------------------------
// Product SKU + base plan constants (single source of truth for the app)
// ---------------------------------------------------------------------------
export const IAP_PRODUCTS = {
  premium: { sku: 'c1_premium', basePlanId: 'monthly' },
  plus_monthly: { sku: 'c1_plus', basePlanId: 'monthly' },
  plus_annual: { sku: 'c1_plus', basePlanId: 'annual' },
} as const;

export type IapKey = keyof typeof IAP_PRODUCTS;

export function skuForKey(key: IapKey): { sku: string; basePlanId: string } {
  return IAP_PRODUCTS[key];
}

export const IAP_PACKAGE_NAME = PACKAGE_NAME;
