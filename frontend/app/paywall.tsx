import { Ionicons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import { LinearGradient } from 'expo-linear-gradient';
import { useRouter } from 'expo-router';
import { useState } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { api } from '@/src/api';
import { useAuth } from '@/src/auth';
import { t } from '@/src/i18n';
import { tokens } from '@/src/theme';

type PlanKey = 'free' | 'premium' | 'plus_monthly' | 'plus_annual';

const PLANS: Array<{
  key: PlanKey;
  tier: 'free' | 'premium' | 'plus';
  title: string;
  price: string;
  priceSub: string;
  highlight?: boolean;
  badge?: string;
  features: string[];
}> = [
  {
    key: 'free',
    tier: 'free',
    title: 'Free',
    price: '€0',
    priceSub: 'forever',
    features: [
      '3 AI meal scans / day',
      '+2 extra scans by watching a short ad',
      'Calorie & macro calculator',
      'Basic food diary',
      'AI Nutrition chat (limited)',
    ],
  },
  {
    key: 'premium',
    tier: 'premium',
    title: 'Premium',
    price: '€1.99',
    priceSub: '/month',
    features: [
      '20 AI meal scans / day',
      '+3 extra scans by watching an ad',
      'Full food diary + water & weight tracking',
      'Full AI Nutrition chat',
      'Reduced ads',
    ],
  },
  {
    key: 'plus_monthly',
    tier: 'plus',
    title: 'Plus',
    price: '€4.99',
    priceSub: '/month',
    highlight: true,
    badge: 'MOST POPULAR',
    features: [
      '99 AI meal scans / day (fair-use)',
      'Zero ads — clean experience',
      'Personalized meal recommendations',
      '"Complete My Day" AI planner',
      'Everything in Premium',
    ],
  },
  {
    key: 'plus_annual',
    tier: 'plus',
    title: 'Plus (Annual)',
    price: '€54.99',
    priceSub: '/year',
    badge: 'BEST VALUE — save ~8%',
    features: [
      'Everything in Plus Monthly',
      'Just €4.58 / month',
      'One yearly payment — no monthly surprise',
    ],
  },
];

export default function Paywall() {
  const router = useRouter();
  const { user, refresh } = useAuth();
  const [selected, setSelected] = useState<PlanKey>('plus_monthly');
  const [busy, setBusy] = useState(false);

  const currentTier: 'free' | 'premium' | 'plus' = user?.plan || 'free';

  const activate = async () => {
    setBusy(true);
    // Phase 1: mock plan-set endpoint removed. Real Apple StoreKit + Google Play Billing
    // integration lands in Phase 2/4. Show a placeholder message.
    Alert.alert(
      'Coming soon',
      'Real in-app purchases will be enabled in the next release. In the current preview, plan changes require a verified store purchase.',
      [{ text: 'OK', onPress: () => router.back() }],
    );
    setBusy(false);
  };

  return (
    <View style={{ flex: 1, backgroundColor: tokens.bg }}>
      <Image
        source={{
          uri: 'https://images.unsplash.com/photo-1648235692910-947cb90ddd97?auto=format&fit=crop&w=1200&q=80',
        }}
        style={StyleSheet.absoluteFill}
        contentFit="cover"
      />
      <LinearGradient
        colors={['rgba(10,10,12,0.35)', 'rgba(10,10,12,0.85)', tokens.bg]}
        style={StyleSheet.absoluteFill}
      />
      <SafeAreaView style={{ flex: 1 }} edges={['top', 'bottom']}>
        <View style={s.header}>
          <Pressable onPress={() => router.back()} style={s.iconBtn} testID="paywall-close">
            <Ionicons name="close" size={22} color={tokens.text} />
          </Pressable>
          <View style={{ width: 40 }} />
        </View>
        <ScrollView contentContainerStyle={s.body}>
          <View style={s.badge}>
            <Ionicons name="star" size={14} color={tokens.onBrand} />
            <Text style={s.badgeText}>C1 SUBSCRIPTION</Text>
          </View>
          <Text style={s.title}>Choose your{'\n'}C1 plan</Text>
          <Text style={s.sub}>AI-powered nutrition coaching. Cancel anytime.</Text>
          <Text style={s.previewNote}>
            Preview prices — actual charge will be the store's localized price at purchase.
          </Text>

          <View style={{ gap: 12 }}>
            {PLANS.map((p) => {
              const isSelected = selected === p.key;
              const isCurrent = currentTier === p.tier;
              return (
                <Pressable
                  key={p.key}
                  testID={`plan-${p.key}`}
                  onPress={() => setSelected(p.key)}
                  style={[
                    s.plan,
                    isSelected && s.planActive,
                    p.highlight && s.planHighlight,
                  ]}
                >
                  {p.badge && (
                    <View style={s.mostPopular}>
                      <Text style={s.mostPopularText}>{p.badge}</Text>
                    </View>
                  )}
                  <View style={s.planHeaderRow}>
                    <Text style={s.planTitle}>{p.title}</Text>
                    {isCurrent && (
                      <View style={s.currentBadge}>
                        <Text style={s.currentBadgeText}>CURRENT</Text>
                      </View>
                    )}
                  </View>
                  <Text style={s.planPrice}>
                    {p.price}
                    <Text style={s.planPriceUnit}> {p.priceSub}</Text>
                  </Text>
                  <View style={{ marginTop: 10, gap: 6 }}>
                    {p.features.map((f, i) => (
                      <View key={i} style={s.featRow}>
                        <Ionicons name="checkmark-circle" size={14} color={tokens.brand} />
                        <Text style={s.featText}>{f}</Text>
                      </View>
                    ))}
                  </View>
                </Pressable>
              );
            })}
          </View>

          <Text style={s.foot}>
            Payments processed by the App Store / Google Play on native builds. This preview uses a
            demo plan selector.
          </Text>
        </ScrollView>

        <View style={s.footer}>
          <Pressable
            testID="paywall-subscribe"
            style={[s.cta, busy && { opacity: 0.5 }]}
            disabled={busy}
            onPress={activate}
          >
            <Text style={s.ctaText}>
              {(() => {
                const sel = PLANS.find((x) => x.key === selected);
                if (!sel) return 'Choose plan';
                if (sel.tier === currentTier) return `Keep ${sel.title}`;
                return `Switch to ${sel.title}`;
              })()}
            </Text>
          </Pressable>
          <Text style={s.restore}>{t('restore')}</Text>
        </View>
      </SafeAreaView>
    </View>
  );
}

const s = StyleSheet.create({
  header: { padding: tokens.md, flexDirection: 'row', justifyContent: 'space-between' },
  iconBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: 'rgba(255,255,255,0.1)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  body: { padding: tokens.lg, paddingBottom: 40, gap: tokens.md },
  badge: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    gap: 4,
    alignItems: 'center',
    backgroundColor: tokens.brand,
    paddingHorizontal: 10,
    height: 26,
    borderRadius: 999,
  },
  badgeText: { color: tokens.onBrand, fontSize: 11, fontWeight: '900', letterSpacing: 1 },
  title: { color: tokens.text, fontSize: 32, fontWeight: '900', letterSpacing: -1, marginTop: 4 },
  sub: { color: tokens.textDim, fontSize: 14, marginBottom: 12 },
  previewNote: {
    color: tokens.textMute,
    fontSize: 11,
    marginTop: -8,
    marginBottom: 8,
    fontStyle: 'italic',
  },
  plan: {
    padding: tokens.lg,
    borderRadius: tokens.rLg,
    backgroundColor: 'rgba(20,20,23,0.85)',
    borderWidth: 2,
    borderColor: tokens.border,
  },
  planActive: { borderColor: tokens.brand, backgroundColor: tokens.brandTint },
  planHighlight: { borderColor: tokens.brand },
  planHeaderRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  planTitle: { color: tokens.text, fontSize: 18, fontWeight: '900' },
  planPrice: { color: tokens.text, fontSize: 28, fontWeight: '900', letterSpacing: -0.5, marginTop: 6 },
  planPriceUnit: { fontSize: 14, fontWeight: '600', color: tokens.textDim },
  featRow: { flexDirection: 'row', gap: 8, alignItems: 'center' },
  featText: { color: tokens.textDim, fontSize: 13, flex: 1 },
  currentBadge: {
    backgroundColor: tokens.bg3,
    paddingHorizontal: 8,
    height: 20,
    borderRadius: 999,
    justifyContent: 'center',
  },
  currentBadgeText: { color: tokens.textDim, fontSize: 9, fontWeight: '900', letterSpacing: 1 },
  mostPopular: {
    position: 'absolute',
    top: -10,
    right: 16,
    backgroundColor: tokens.brand,
    paddingHorizontal: 10,
    height: 22,
    borderRadius: 999,
    justifyContent: 'center',
  },
  mostPopularText: { color: tokens.onBrand, fontSize: 9, fontWeight: '900', letterSpacing: 1 },
  foot: { color: tokens.textMute, fontSize: 11, lineHeight: 16, marginTop: 12 },
  footer: { padding: tokens.lg, gap: 10 },
  cta: {
    backgroundColor: tokens.brand,
    height: 56,
    borderRadius: tokens.rLg,
    alignItems: 'center',
    justifyContent: 'center',
  },
  ctaText: { color: tokens.onBrand, fontSize: 16, fontWeight: '900' },
  restore: { color: tokens.textDim, fontSize: 13, textAlign: 'center' },
});
