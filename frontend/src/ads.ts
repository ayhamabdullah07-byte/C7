/**
 * AdMob wrapper — Rewarded + Interstitial ads with graceful Expo Go fallback.
 *
 * The `react-native-google-mobile-ads` module contains native code that ONLY works
 * in a production/development build (Expo Prebuild), NOT inside Expo Go.
 * We import it lazily so the app still runs in Expo Go — ad-related actions
 * will simply return {available:false} and callers can show a graceful message.
 */
import Constants from 'expo-constants';
import { Platform } from 'react-native';

// ---------------------------------------------------------------------------
// Extra config from app.json
// ---------------------------------------------------------------------------
const extra = (Constants.expoConfig?.extra || {}) as Record<string, any>;
const ADMOB = (extra.admob || {}) as {
  androidAppId?: string;
  iosAppId?: string;
  rewardedUnitId?: string;
  interstitialUnitId?: string;
  iosRewardedTestUnitId?: string;
  iosInterstitialTestUnitId?: string;
};

// Prefer the real Android IDs. iOS falls back to Google's official test units
// until the user creates the iOS AdMob app in their AdMob console.
export const REWARDED_UNIT_ID =
  Platform.OS === 'ios'
    ? ADMOB.iosRewardedTestUnitId || 'ca-app-pub-3940256099942544/1712485313'
    : ADMOB.rewardedUnitId || 'ca-app-pub-3940256099942544/5224354917';

export const INTERSTITIAL_UNIT_ID =
  Platform.OS === 'ios'
    ? ADMOB.iosInterstitialTestUnitId || 'ca-app-pub-3940256099942544/4411468910'
    : ADMOB.interstitialUnitId || 'ca-app-pub-3940256099942544/1033173712';

// ---------------------------------------------------------------------------
// Lazy native module load — protected against Expo Go / web
// ---------------------------------------------------------------------------
type NativeAds = typeof import('react-native-google-mobile-ads');

let nativeMod: NativeAds | null = null;
let nativeChecked = false;
let nativeInitPromise: Promise<boolean> | null = null;

function loadNative(): NativeAds | null {
  if (nativeChecked) return nativeMod;
  nativeChecked = true;
  try {
    // Detect Expo Go — it can't run native modules like this one.
    const appOwnership = (Constants as any).appOwnership;
    const isExpoGo = appOwnership === 'expo';
    if (isExpoGo || Platform.OS === 'web') {
      return null;
    }
    // Dynamic require so bundler still resolves it but crash is caught if unavailable.
    const mod = require('react-native-google-mobile-ads') as NativeAds;
    // Sanity: check the default export & MobileAds helper are present.
    if (!mod || typeof (mod as any).default !== 'function') {
      return null;
    }
    nativeMod = mod;
    return mod;
  } catch (e) {
    // Native module not linked (Expo Go, web, snack, first boot before prebuild).
    console.warn('[ads] native module unavailable — running in fallback mode', e);
    return null;
  }
}

/**
 * True only in a native build with the SDK linked. False in Expo Go / web.
 */
export function adsAvailable(): boolean {
  return loadNative() !== null;
}

/**
 * One-time SDK init. Safe to call many times.
 */
export async function initAds(): Promise<boolean> {
  const mod = loadNative();
  if (!mod) return false;
  if (nativeInitPromise) return nativeInitPromise;
  nativeInitPromise = (async () => {
    try {
      const MobileAds = (mod as any).default;
      await MobileAds().initialize();
      return true;
    } catch (e) {
      console.warn('[ads] initialize failed', e);
      return false;
    }
  })();
  return nativeInitPromise;
}

// ---------------------------------------------------------------------------
// Rewarded Ad
// ---------------------------------------------------------------------------
export type RewardedResult =
  | { status: 'rewarded'; amount: number; type: string }
  | { status: 'closed_no_reward' }
  | { status: 'failed_to_load'; error: string }
  | { status: 'sdk_unavailable' };

/**
 * Load + show a rewarded ad with the user's SSV token embedded as `customData`.
 * Resolves once the ad flow is complete (rewarded, closed without reward, or error).
 *
 * When the SDK is not available (Expo Go / web), immediately resolves with
 * `{status:'sdk_unavailable'}` so the UI can show a friendly message.
 */
export async function showRewardedAd(customData: string): Promise<RewardedResult> {
  const mod = loadNative();
  if (!mod) return { status: 'sdk_unavailable' };
  try {
    await initAds();
    const { RewardedAd, RewardedAdEventType, AdEventType } = mod as any;
    const ad = RewardedAd.createForAdRequest(REWARDED_UNIT_ID, {
      requestNonPersonalizedAdsOnly: false,
      keywords: ['nutrition', 'health', 'food'],
      serverSideVerificationOptions: { customData },
    });

    return await new Promise<RewardedResult>((resolve) => {
      let rewarded = false;
      let settled = false;
      const finish = (r: RewardedResult) => {
        if (settled) return;
        settled = true;
        try {
          unsubLoaded?.();
          unsubReward?.();
          unsubClosed?.();
          unsubError?.();
        } catch {}
        resolve(r);
      };
      const unsubLoaded = ad.addAdEventListener(RewardedAdEventType.LOADED, () => {
        try {
          ad.show();
        } catch (e: any) {
          finish({ status: 'failed_to_load', error: String(e?.message || e) });
        }
      });
      const unsubReward = ad.addAdEventListener(
        RewardedAdEventType.EARNED_REWARD,
        (reward: any) => {
          rewarded = true;
          finish({
            status: 'rewarded',
            amount: reward?.amount ?? 1,
            type: reward?.type || 'scan',
          });
        },
      );
      const unsubClosed = ad.addAdEventListener(AdEventType.CLOSED, () => {
        if (!rewarded) finish({ status: 'closed_no_reward' });
      });
      const unsubError = ad.addAdEventListener(AdEventType.ERROR, (err: any) => {
        finish({ status: 'failed_to_load', error: String(err?.message || err) });
      });
      // Start loading
      try {
        ad.load();
      } catch (e: any) {
        finish({ status: 'failed_to_load', error: String(e?.message || e) });
      }
    });
  } catch (e: any) {
    return { status: 'failed_to_load', error: String(e?.message || e) };
  }
}

// ---------------------------------------------------------------------------
// Interstitial Ad (used after Free user's 2nd scan)
// ---------------------------------------------------------------------------
export async function showInterstitialAd(): Promise<boolean> {
  const mod = loadNative();
  if (!mod) return false;
  try {
    await initAds();
    const { InterstitialAd, AdEventType } = mod as any;
    const ad = InterstitialAd.createForAdRequest(INTERSTITIAL_UNIT_ID, {
      requestNonPersonalizedAdsOnly: false,
    });
    return await new Promise<boolean>((resolve) => {
      let settled = false;
      const finish = (v: boolean) => {
        if (settled) return;
        settled = true;
        try {
          unsubLoaded?.();
          unsubClosed?.();
          unsubError?.();
        } catch {}
        resolve(v);
      };
      const unsubLoaded = ad.addAdEventListener(AdEventType.LOADED, () => {
        try {
          ad.show();
        } catch {
          finish(false);
        }
      });
      const unsubClosed = ad.addAdEventListener(AdEventType.CLOSED, () => finish(true));
      const unsubError = ad.addAdEventListener(AdEventType.ERROR, () => finish(false));
      try {
        ad.load();
      } catch {
        finish(false);
      }
    });
  } catch {
    return false;
  }
}
