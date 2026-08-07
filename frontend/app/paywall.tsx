import { Ionicons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import { LinearGradient } from 'expo-linear-gradient';
import { useRouter } from 'expo-router';
import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { api } from '@/src/api';
import { useAuth } from '@/src/auth';
import { t } from '@/src/i18n';
import { tokens } from '@/src/theme';

const FEATURES = [
  'AI Meal Scanner (Camera → Nutrition)',
  'AI Nutrition Assistant Chat',
  'Personal AI Coach',
  'Personalized Meal Plans',
  'Unlimited Food Diary',
  'Weight & Body Measurements',
  'Progress Photos & Analytics',
  'Cloud Backup & Sync',
];

export default function Paywall() {
  const router = useRouter();
  const { user, refresh } = useAuth();
  const [plan, setPlan] = useState<'intro' | 'monthly'>('intro');
  const [busy, setBusy] = useState(false);

  const subscribe = async () => {
    setBusy(true);
    try {
      // MOCKED: real Apple/Google IAP wires in native build via Emergent publish flow.
      await api.togglePremium();
      await refresh();
      router.back();
    } catch {}
    setBusy(false);
  };

  return (
    <View style={{ flex: 1, backgroundColor: tokens.bg }}>
      <Image
        source={{ uri: 'https://images.unsplash.com/photo-1648235692910-947cb90ddd97?auto=format&fit=crop&w=1200&q=80' }}
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
            <Text style={s.badgeText}>C1 PREMIUM</Text>
          </View>
          <Text style={s.title}>Unlock the full{'\n'}C1 experience</Text>
          <Text style={s.sub}>AI-powered nutrition coaching tuned to your goals.</Text>

          <View style={s.features}>
            {FEATURES.map((f) => (
              <View key={f} style={s.featRow}>
                <View style={s.featIcon}>
                  <Ionicons name="checkmark" size={14} color={tokens.brand} />
                </View>
                <Text style={s.featText}>{f}</Text>
              </View>
            ))}
          </View>

          <View style={s.plans}>
            <Pressable
              testID="plan-intro"
              style={[s.plan, plan === 'intro' && s.planActive]}
              onPress={() => setPlan('intro')}
            >
              <View style={s.planHeader}>
                <Text style={s.planTitle}>3 Months</Text>
                <View style={s.saveBadge}>
                  <Text style={s.saveText}>SAVE 17%</Text>
                </View>
              </View>
              <Text style={s.planPrice}>€4.99</Text>
              <Text style={s.planSub}>First-time offer · one time</Text>
            </Pressable>
            <Pressable
              testID="plan-monthly"
              style={[s.plan, plan === 'monthly' && s.planActive]}
              onPress={() => setPlan('monthly')}
            >
              <Text style={s.planTitle}>Monthly</Text>
              <Text style={s.planPrice}>€1.99<Text style={s.planUnit}>/mo</Text></Text>
              <Text style={s.planSub}>Cancel anytime</Text>
            </Pressable>
          </View>

          <Text style={s.foot}>
            Payments are processed by the App Store / Google Play on native builds. This preview uses a demo toggle.
          </Text>
        </ScrollView>

        <View style={s.footer}>
          <Pressable
            testID="paywall-subscribe"
            style={[s.cta, busy && { opacity: 0.5 }]}
            disabled={busy}
            onPress={subscribe}
          >
            <Text style={s.ctaText}>
              {user?.premium ? t('managePremium') : `Start Premium · ${plan === 'intro' ? '€4.99' : '€1.99/mo'}`}
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
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: 'rgba(255,255,255,0.1)', alignItems: 'center', justifyContent: 'center',
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
  title: { color: tokens.text, fontSize: 34, fontWeight: '900', letterSpacing: -1, marginTop: 6 },
  sub: { color: tokens.textDim, fontSize: 15, marginBottom: 12 },
  features: {
    backgroundColor: 'rgba(20,20,23,0.7)',
    borderRadius: tokens.rLg,
    padding: tokens.lg,
    gap: 12,
    borderWidth: 1,
    borderColor: tokens.border,
  },
  featRow: { flexDirection: 'row', gap: 10, alignItems: 'center' },
  featIcon: {
    width: 22, height: 22, borderRadius: 11,
    backgroundColor: tokens.brandTint, alignItems: 'center', justifyContent: 'center',
  },
  featText: { color: tokens.text, fontSize: 14, fontWeight: '600', flex: 1 },
  plans: { flexDirection: 'row', gap: 10, marginTop: 6 },
  plan: {
    flex: 1,
    padding: tokens.md,
    borderRadius: tokens.rLg,
    backgroundColor: 'rgba(20,20,23,0.85)',
    borderWidth: 2,
    borderColor: tokens.border,
  },
  planActive: { borderColor: tokens.brand, backgroundColor: tokens.brandTint },
  planHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  planTitle: { color: tokens.text, fontSize: 14, fontWeight: '800' },
  saveBadge: { backgroundColor: tokens.brand, paddingHorizontal: 6, borderRadius: 4, height: 18, justifyContent: 'center' },
  saveText: { color: tokens.onBrand, fontSize: 9, fontWeight: '900' },
  planPrice: { color: tokens.text, fontSize: 26, fontWeight: '900', marginTop: 6, letterSpacing: -0.5 },
  planUnit: { fontSize: 14, fontWeight: '700', color: tokens.textDim },
  planSub: { color: tokens.textMute, fontSize: 11, marginTop: 4 },
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
