import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useState } from 'react';
import {
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { api } from '@/src/api';
import { useAuth } from '@/src/auth';
import { t } from '@/src/i18n';
import { CalorieRing, MacroBar } from '@/src/rings';
import { macroColors, tokens } from '@/src/theme';

function today() {
  return new Date().toISOString().slice(0, 10);
}

export default function Home() {
  const router = useRouter();
  const { user } = useAuth();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const d = await api.dashboard(today());
      setData(d);
      setErr(null);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const targets = data?.targets;
  const totals = data?.totals || { calories: 0, protein_g: 0, carbs_g: 0, fat_g: 0 };
  const waterMl = data?.water_ml || 0;

  const addWater = async () => {
    try {
      await api.addWater(today(), 250);
      load();
    } catch {}
  };

  return (
    <SafeAreaView style={s.wrap} edges={['top']}>
      <ScrollView
        contentContainerStyle={s.body}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor={tokens.brand} />}
      >
        <View style={s.header}>
          <View>
            <Text style={s.hello} testID="home-greeting">Hello, {user?.name?.split(' ')[0] || 'friend'}</Text>
            <Text style={s.date}>
              {new Date().toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })}
            </Text>
          </View>
          <View style={s.streakBadge} testID="streak-badge">
            <Ionicons name="flame" size={14} color={tokens.brand} />
            <Text style={s.streakText}>{data?.streak ?? 0}</Text>
          </View>
        </View>

        <View style={s.ringCard} testID="calorie-card">
          <CalorieRing
            consumed={totals.calories}
            target={targets?.calories ?? 2000}
            label={t('caloriesLeft')}
            sub={`${Math.round(totals.calories)} / ${targets?.calories ?? '—'}`}
          />
        </View>

        <View style={s.macros} testID="macros-card">
          <MacroBar
            name={t('protein')}
            value={totals.protein_g}
            target={targets?.protein_g ?? 100}
            color={macroColors.protein}
          />
          <MacroBar
            name={t('carbs')}
            value={totals.carbs_g}
            target={targets?.carbs_g ?? 250}
            color={macroColors.carbs}
          />
          <MacroBar
            name={t('fat')}
            value={totals.fat_g}
            target={targets?.fat_g ?? 70}
            color={macroColors.fat}
          />
        </View>

        <Pressable
          onPress={() => router.push('/scan')}
          style={s.hero}
          testID="home-scan-hero"
        >
          <View>
            <Text style={s.heroTitle}>{t('scan')}</Text>
            <Text style={s.heroSub}>Point your camera at any meal</Text>
          </View>
          <View style={s.heroIcon}>
            <Ionicons name="camera" size={26} color={tokens.onBrand} />
          </View>
        </Pressable>

        <Pressable
          onPress={() => router.push(user?.premium ? '/recommend' : '/paywall')}
          style={s.completeCard}
          testID="home-complete-day"
        >
          <View style={s.completeIcon}>
            <Text style={{ fontSize: 26 }}>🎯</Text>
          </View>
          <View style={{ flex: 1 }}>
            <View style={s.completeTitleRow}>
              <Text style={s.completeTitle}>Complete My Day</Text>
              {!user?.premium && (
                <View style={s.premiumTag}>
                  <Ionicons name="star" size={9} color={tokens.onBrand} />
                  <Text style={s.premiumTagText}>PREMIUM</Text>
                </View>
              )}
            </View>
            <Text style={s.completeSub}>
              AI meal & snack ideas to hit today's targets
            </Text>
          </View>
          <Ionicons name="chevron-forward" size={18} color={tokens.textDim} />
        </Pressable>

        <View style={s.row2}>
          <View style={[s.miniCard, { flex: 1 }]} testID="water-card">
            <View style={s.miniHeader}>
              <Ionicons name="water" size={16} color={macroColors.water} />
              <Text style={s.miniLabel}>{t('water')}</Text>
            </View>
            <Text style={s.miniVal}>
              {waterMl} <Text style={s.miniUnit}>/ {targets?.water_ml ?? 2500} ml</Text>
            </Text>
            <View style={s.track}>
              <View
                style={[
                  s.fill,
                  {
                    width: `${Math.min(100, (waterMl / (targets?.water_ml || 2500)) * 100)}%`,
                    backgroundColor: macroColors.water,
                  },
                ]}
              />
            </View>
            <Pressable style={s.waterBtn} onPress={addWater} testID="add-water-btn">
              <Ionicons name="add" size={16} color={tokens.text} />
              <Text style={s.waterBtnText}>+250 ml</Text>
            </Pressable>
          </View>
          <View style={[s.miniCard, { flex: 1 }]} testID="weight-card">
            <View style={s.miniHeader}>
              <Ionicons name="body" size={16} color={tokens.brand} />
              <Text style={s.miniLabel}>{t('weight')}</Text>
            </View>
            <Text style={s.miniVal}>
              {user?.weight_kg ?? '—'} <Text style={s.miniUnit}>kg</Text>
            </Text>
            <Text style={s.miniSub}>Target {user?.target_weight_kg ?? '—'} kg</Text>
          </View>
        </View>

        <Text style={s.foot}>{t('medicalDisclaimer')}</Text>
        {err && <Text style={{ color: tokens.danger }}>{err}</Text>}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: tokens.bg },
  body: { padding: tokens.lg, paddingBottom: 140, gap: tokens.lg },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: tokens.sm,
  },
  hello: { color: tokens.text, fontSize: 22, fontWeight: '800', letterSpacing: -0.5 },
  date: { color: tokens.textMute, fontSize: 13, marginTop: 2 },
  streakBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 10,
    height: 32,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: tokens.border,
    backgroundColor: tokens.bg2,
  },
  streakText: { color: tokens.text, fontWeight: '800', fontSize: 13 },
  ringCard: {
    backgroundColor: tokens.bg2,
    borderRadius: tokens.rLg,
    padding: tokens.lg,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: tokens.border,
  },
  macros: {
    backgroundColor: tokens.bg2,
    borderRadius: tokens.rLg,
    padding: tokens.lg,
    borderWidth: 1,
    borderColor: tokens.border,
  },
  hero: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: tokens.lg,
    borderRadius: tokens.rLg,
    backgroundColor: tokens.brand,
  },
  heroTitle: { color: tokens.onBrand, fontSize: 20, fontWeight: '900' },
  heroSub: { color: 'rgba(10,10,12,0.7)', fontSize: 13, marginTop: 2, fontWeight: '600' },
  heroIcon: {
    width: 52,
    height: 52,
    borderRadius: 16,
    backgroundColor: 'rgba(10,10,12,0.15)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  completeCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    padding: tokens.md,
    borderRadius: tokens.rLg,
    backgroundColor: tokens.bg2,
    borderWidth: 1,
    borderColor: tokens.border,
  },
  completeIcon: {
    width: 52,
    height: 52,
    borderRadius: 16,
    backgroundColor: tokens.brandTint,
    borderWidth: 1,
    borderColor: tokens.brand,
    alignItems: 'center',
    justifyContent: 'center',
  },
  completeTitleRow: { flexDirection: 'row', gap: 6, alignItems: 'center' },
  completeTitle: { color: tokens.text, fontSize: 15, fontWeight: '800' },
  completeSub: { color: tokens.textMute, fontSize: 12, marginTop: 2 },
  premiumTag: {
    flexDirection: 'row',
    gap: 2,
    alignItems: 'center',
    backgroundColor: tokens.brand,
    paddingHorizontal: 6,
    height: 16,
    borderRadius: 4,
  },
  premiumTagText: { color: tokens.onBrand, fontSize: 8, fontWeight: '900', letterSpacing: 0.5 },
  row2: { flexDirection: 'row', gap: tokens.md },
  miniCard: {
    backgroundColor: tokens.bg2,
    borderRadius: tokens.rLg,
    padding: tokens.lg,
    borderWidth: 1,
    borderColor: tokens.border,
    gap: 8,
  },
  miniHeader: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  miniLabel: { color: tokens.textDim, fontSize: 12, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 },
  miniVal: { color: tokens.text, fontSize: 22, fontWeight: '800', letterSpacing: -0.5 },
  miniUnit: { color: tokens.textMute, fontSize: 12, fontWeight: '600' },
  miniSub: { color: tokens.textMute, fontSize: 11 },
  track: { height: 6, backgroundColor: tokens.bg3, borderRadius: 999, overflow: 'hidden', marginTop: 4 },
  fill: { height: '100%', borderRadius: 999 },
  waterBtn: {
    marginTop: 6,
    height: 32,
    borderRadius: 999,
    backgroundColor: tokens.bg3,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 4,
  },
  waterBtnText: { color: tokens.text, fontSize: 12, fontWeight: '700' },
  foot: { color: tokens.textMute, fontSize: 11, lineHeight: 16, marginTop: tokens.md },
});
