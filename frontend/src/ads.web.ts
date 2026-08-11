/**
 * Web stub for the AdMob wrapper — react-native-google-mobile-ads is native-only.
 * On the web preview we always report the SDK as unavailable; the LimitDialog
 * falls back to the dev-only SSV path so the flow can still be exercised.
 */

export const REWARDED_UNIT_ID = 'web-stub';
export const INTERSTITIAL_UNIT_ID = 'web-stub';

export function adsAvailable(): boolean {
  return false;
}

export async function initAds(): Promise<boolean> {
  return false;
}

export type RewardedResult =
  | { status: 'rewarded'; amount: number; type: string }
  | { status: 'closed_no_reward' }
  | { status: 'failed_to_load'; error: string }
  | { status: 'sdk_unavailable' };

export async function showRewardedAd(_customData: string): Promise<RewardedResult> {
  return { status: 'sdk_unavailable' };
}

export async function showInterstitialAd(): Promise<boolean> {
  return false;
}
