/**
 * Web stub for the Google Play Billing wrapper.
 * react-native-iap is native-only; on web we always report unavailable.
 */
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
    billingPeriod?: string;
  }>;
};

export type PurchaseResult =
  | { status: 'success'; plan: 'premium' | 'plus'; period?: 'P1M' | 'P1Y' }
  | { status: 'user_cancelled' }
  | { status: 'unavailable'; reason: string }
  | { status: 'failed'; error: string };

export function billingAvailable(): boolean {
  return false;
}

export async function initBilling(): Promise<boolean> {
  return false;
}

export async function fetchSubscriptions(_skus: string[]): Promise<SubProduct[]> {
  return [];
}

export async function requestSubscriptionPurchase(
  _sku: string,
  _basePlanId?: string,
): Promise<PurchaseResult> {
  return {
    status: 'unavailable',
    reason:
      'Google Play purchases require an Android production/internal-testing build. Use the "Publish" button to generate an Android build.',
  };
}

export const IAP_PRODUCTS = {
  premium: { sku: 'c1_premium', basePlanId: 'monthly' },
  plus_monthly: { sku: 'c1_plus', basePlanId: 'monthly' },
  plus_annual: { sku: 'c1_plus', basePlanId: 'annual' },
} as const;

export type IapKey = keyof typeof IAP_PRODUCTS;

export function skuForKey(key: IapKey) {
  return IAP_PRODUCTS[key];
}

export const IAP_PACKAGE_NAME = 'com.ayhamabdullah.c1';
