import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Animated,
  Modal,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { adsAvailable, showRewardedAd } from './ads';
import { api } from './api';
import { t } from './i18n';
import { tokens } from './theme';

export type LimitReason =
  | 'base_limit_reached'    // Free/Premium — base gone, ad still available
  | 'scan_limit_reached'    // total cap hit (Free/Premium AND Plus)
  | 'unknown';

export type LimitPlan = 'free' | 'premium' | 'plus';

export type LimitDialogState = {
  visible: boolean;
  reason: LimitReason;
  plan: LimitPlan;
  baseLimit: number;      // base per-day
  rewardedLimit: number;  // rewarded per-day
  fairUseLimit: number;   // base + rewarded (or plus cap)
  canWatchAd: boolean;
  resetAt?: string | null;
};

export type LimitDialogProps = LimitDialogState & {
  onClose: () => void;
  onSubscribe: () => void;
  /** Called after a successful rewarded credit was granted — parent should retry the scan. */
  onRewardGranted: () => void;
};

function fmtCountdown(resetAt?: string | null): string | null {
  if (!resetAt) return null;
  const target = new Date(resetAt).getTime();
  const now = Date.now();
  const diff = Math.max(0, target - now);
  const hrs = Math.floor(diff / 3_600_000);
  const mins = Math.floor((diff % 3_600_000) / 60_000);
  if (hrs > 0) return `${hrs}h ${mins}m`;
  return `${mins}m`;
}

export function LimitDialog(props: LimitDialogProps) {
  const { visible, reason, plan, baseLimit, fairUseLimit, canWatchAd, resetAt } = props;
  const [busy, setBusy] = useState<'idle' | 'loading_ad' | 'redeeming'>('idle');
  const [adError, setAdError] = useState<string | null>(null);
  const fadeAnim = useRef(new Animated.Value(0)).current;
  const scaleAnim = useRef(new Animated.Value(0.92)).current;

  useEffect(() => {
    if (visible) {
      setBusy('idle');
      setAdError(null);
      Animated.parallel([
        Animated.timing(fadeAnim, { toValue: 1, duration: 180, useNativeDriver: true }),
        Animated.spring(scaleAnim, { toValue: 1, useNativeDriver: true, bounciness: 6 }),
      ]).start();
    } else {
      fadeAnim.setValue(0);
      scaleAnim.setValue(0.92);
    }
  }, [visible, fadeAnim, scaleAnim]);

  // Choose i18n-localized message
  const message = useMemo(() => {
    if (plan === 'plus') return t('scanLimitPlusMsg').replace('{total}', String(fairUseLimit));
    if (reason === 'base_limit_reached' || canWatchAd) {
      const key = plan === 'premium' ? 'scanLimitPremiumMsg' : 'scanLimitFreeMsg';
      return t(key).replace('{base}', String(baseLimit));
    }
    // fully capped
    return t('scanCapAllReachedMsg').replace('{total}', String(fairUseLimit));
  }, [plan, reason, canWatchAd, baseLimit, fairUseLimit]);

  const countdown = fmtCountdown(resetAt);

  const handleWatchAd = useCallback(async () => {
    setAdError(null);
    setBusy('loading_ad');
    try {
      // 1. Get short-lived SSV token from backend
      const tokRes = await api.rewardedToken();
      const customData: string = tokRes.token;

      // 2. Show rewarded ad
      const result = await showRewardedAd(customData);

      if (result.status === 'rewarded') {
        // AdMob's servers will call our /rewarded/redeem SSV endpoint.
        // Give it a moment then confirm via quota.
        setBusy('redeeming');
        // brief settle for SSV
        await new Promise((r) => setTimeout(r, 900));
        props.onRewardGranted();
        return;
      }
      if (result.status === 'closed_no_reward') {
        setBusy('idle');
        setAdError(t('adFailed'));
        return;
      }
      if (result.status === 'sdk_unavailable') {
        // Expo Go / preview — SDK isn't linked. Fall back to a dev-only SSV redeem
        // so the flow can be verified end-to-end. In a real production build,
        // AdMob's server (not the client) hits /rewarded/redeem after a real reward.
        setBusy('redeeming');
        try {
          const txId = `dev-${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
          await api.rewardedRedeemDev(txId, customData);
          await new Promise((r) => setTimeout(r, 250));
          props.onRewardGranted();
        } catch (e: any) {
          setBusy('idle');
          setAdError(
            e?.detail || e?.message || t('adFailed'),
          );
        }
        return;
      }
      // failed_to_load or any other
      setBusy('idle');
      setAdError(t('adFailed'));
    } catch (e: any) {
      setBusy('idle');
      setAdError(e?.message || t('adFailed'));
    }
  }, [props]);

  if (!visible) return null;

  // If SDK not present AND we still show WATCH AD, add a subtle preview hint.
  const showPreviewHint = canWatchAd && !adsAvailable();

  return (
    <Modal
      visible={visible}
      transparent
      animationType="none"
      statusBarTranslucent
      onRequestClose={props.onClose}
    >
      <Animated.View style={[s.backdrop, { opacity: fadeAnim }]}>
        <Pressable style={StyleSheet.absoluteFill} onPress={busy === 'idle' ? props.onClose : undefined} />
        <Animated.View
          style={[
            s.sheet,
            {
              opacity: fadeAnim,
              transform: [{ scale: scaleAnim }],
            },
          ]}
        >
          <LinearGradient
            colors={['rgba(212,175,55,0.14)', 'rgba(212,175,55,0)']}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={s.gradient}
          />
          <View style={s.iconCircle}>
            <Ionicons name="hourglass-outline" size={26} color={tokens.brand} />
          </View>
          <Text style={s.title}>{t('scanLimitTitle')}</Text>
          <Text style={s.body}>{message}</Text>

          {countdown && (
            <View style={s.countdownPill}>
              <Ionicons name="time-outline" size={13} color={tokens.textDim} />
              <Text style={s.countdownText}>
                {t('resetsIn').replace('{time}', countdown)}
              </Text>
            </View>
          )}

          {adError && (
            <View style={s.errorRow}>
              <Ionicons name="alert-circle-outline" size={14} color={tokens.danger} />
              <Text style={s.errorText}>{adError}</Text>
            </View>
          )}

          {showPreviewHint && !adError && (
            <Text style={s.previewHint}>
              {Platform.OS === 'web'
                ? 'Rewarded ads require a native build. In preview, the reward will be simulated.'
                : 'Preview build: reward is simulated. Real ads render in production build.'}
            </Text>
          )}

          <View style={s.actions}>
            {canWatchAd && (
              <Pressable
                testID="limit-watch-ad"
                onPress={handleWatchAd}
                disabled={busy !== 'idle'}
                style={({ pressed }) => [
                  s.btnPrimary,
                  busy !== 'idle' && { opacity: 0.6 },
                  pressed && !busy && { transform: [{ scale: 0.985 }] },
                ]}
              >
                {busy === 'idle' && (
                  <>
                    <Ionicons name="play-circle" size={20} color={tokens.onBrand} />
                    <Text style={s.btnPrimaryText}>{t('watchAdEarnScan')}</Text>
                  </>
                )}
                {busy === 'loading_ad' && (
                  <>
                    <ActivityIndicator color={tokens.onBrand} size="small" />
                    <Text style={s.btnPrimaryText}>{t('watchingAd')}</Text>
                  </>
                )}
                {busy === 'redeeming' && (
                  <>
                    <ActivityIndicator color={tokens.onBrand} size="small" />
                    <Text style={s.btnPrimaryText}>{t('watchingAd')}</Text>
                  </>
                )}
              </Pressable>
            )}

            {plan !== 'plus' && (
              <Pressable
                testID="limit-view-plans"
                onPress={props.onSubscribe}
                disabled={busy !== 'idle'}
                style={({ pressed }) => [
                  canWatchAd ? s.btnSecondary : s.btnPrimary,
                  busy !== 'idle' && { opacity: 0.6 },
                  pressed && !busy && { transform: [{ scale: 0.985 }] },
                ]}
              >
                <Ionicons
                  name="star"
                  size={18}
                  color={canWatchAd ? tokens.brand : tokens.onBrand}
                />
                <Text style={canWatchAd ? s.btnSecondaryText : s.btnPrimaryText}>
                  {t('upgradeForMore')}
                </Text>
              </Pressable>
            )}

            <Pressable
              testID="limit-close"
              onPress={props.onClose}
              disabled={busy !== 'idle'}
              style={({ pressed }) => [
                s.btnGhost,
                busy !== 'idle' && { opacity: 0.4 },
                pressed && !busy && { transform: [{ scale: 0.98 }] },
              ]}
            >
              <Text style={s.btnGhostText}>Close</Text>
            </Pressable>
          </View>
        </Animated.View>
      </Animated.View>
    </Modal>
  );
}

const s = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.72)',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 20,
  },
  sheet: {
    width: '100%',
    maxWidth: 420,
    backgroundColor: tokens.bg2,
    borderRadius: 24,
    padding: 24,
    borderWidth: 1,
    borderColor: tokens.border,
    overflow: 'hidden',
    alignItems: 'center',
  },
  gradient: {
    ...StyleSheet.absoluteFillObject,
  },
  iconCircle: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: tokens.brandTint,
    borderWidth: 1,
    borderColor: tokens.brand,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 14,
  },
  title: {
    color: tokens.text,
    fontSize: 20,
    fontWeight: '900',
    letterSpacing: -0.3,
    textAlign: 'center',
    marginBottom: 8,
  },
  body: {
    color: tokens.textDim,
    fontSize: 14,
    lineHeight: 20,
    textAlign: 'center',
    marginBottom: 12,
    paddingHorizontal: 4,
  },
  countdownPill: {
    flexDirection: 'row',
    gap: 5,
    alignItems: 'center',
    backgroundColor: tokens.bg3,
    paddingHorizontal: 10,
    height: 26,
    borderRadius: 999,
    marginBottom: 4,
  },
  countdownText: { color: tokens.textDim, fontSize: 12, fontWeight: '600' },
  previewHint: {
    color: tokens.textMute,
    fontSize: 11,
    marginTop: 6,
    fontStyle: 'italic',
    textAlign: 'center',
    paddingHorizontal: 6,
  },
  errorRow: {
    flexDirection: 'row',
    gap: 6,
    alignItems: 'center',
    marginTop: 8,
    paddingHorizontal: 6,
  },
  errorText: { color: tokens.danger, fontSize: 12, flexShrink: 1 },
  actions: {
    marginTop: 18,
    width: '100%',
    gap: 10,
  },
  btnPrimary: {
    height: 52,
    borderRadius: 14,
    backgroundColor: tokens.brand,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 8,
    paddingHorizontal: 16,
  },
  btnPrimaryText: { color: tokens.onBrand, fontSize: 15, fontWeight: '800' },
  btnSecondary: {
    height: 52,
    borderRadius: 14,
    backgroundColor: tokens.brandTint,
    borderWidth: 1,
    borderColor: tokens.brand,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 8,
    paddingHorizontal: 16,
  },
  btnSecondaryText: { color: tokens.brand, fontSize: 15, fontWeight: '800' },
  btnGhost: {
    height: 42,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  btnGhostText: { color: tokens.textDim, fontSize: 14, fontWeight: '600' },
});
