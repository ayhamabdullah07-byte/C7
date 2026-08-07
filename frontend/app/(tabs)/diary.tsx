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
import { t } from '@/src/i18n';
import { tokens } from '@/src/theme';

const MEALS: Array<{ key: 'breakfast' | 'lunch' | 'dinner' | 'snack'; icon: any }> = [
  { key: 'breakfast', icon: 'sunny' },
  { key: 'lunch', icon: 'partly-sunny' },
  { key: 'dinner', icon: 'moon' },
  { key: 'snack', icon: 'ice-cream' },
];

function today() {
  return new Date().toISOString().slice(0, 10);
}

export default function Diary() {
  const router = useRouter();
  const [meals, setMeals] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const list = await api.listMeals(today());
      setMeals(list);
    } catch {}
    setLoading(false);
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const grouped = MEALS.map((m) => ({
    ...m,
    items: meals.filter((x) => x.meal_type === m.key),
  }));

  const deleteMeal = async (id: string) => {
    try {
      await api.deleteMeal(id);
      load();
    } catch {}
  };

  return (
    <SafeAreaView style={s.wrap} edges={['top']}>
      <View style={s.header}>
        <Text style={s.title}>{t('diary')}</Text>
        <Text style={s.date}>
          {new Date().toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'short' })}
        </Text>
      </View>
      <ScrollView
        contentContainerStyle={s.body}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor={tokens.brand} />}
      >
        {meals.length === 0 && !loading && (
          <View style={s.empty} testID="diary-empty">
            <Ionicons name="restaurant-outline" size={40} color={tokens.textMute} />
            <Text style={s.emptyText}>{t('noMealsYet')}</Text>
            <Pressable style={s.emptyBtn} onPress={() => router.push('/scan')} testID="diary-scan-btn">
              <Ionicons name="camera" size={18} color={tokens.onBrand} />
              <Text style={s.emptyBtnText}>{t('scan')}</Text>
            </Pressable>
          </View>
        )}

        {grouped.map((g) => (
          <View key={g.key} style={s.group}>
            <View style={s.groupHeader}>
              <View style={s.groupHeaderLeft}>
                <Ionicons name={g.icon} size={16} color={tokens.brand} />
                <Text style={s.groupTitle}>{t(g.key)}</Text>
              </View>
              <Text style={s.groupTotal}>
                {Math.round(g.items.reduce((a: number, m: any) => a + m.total_calories, 0))} kcal
              </Text>
            </View>
            {g.items.length === 0 ? (
              <Pressable style={s.groupEmpty} onPress={() => router.push('/scan')}>
                <Ionicons name="add-circle-outline" size={18} color={tokens.textMute} />
                <Text style={s.groupEmptyText}>Add {t(g.key).toLowerCase()}</Text>
              </Pressable>
            ) : (
              g.items.map((m: any) => (
                <View key={m.id} style={s.mealRow} testID={`meal-row-${m.id}`}>
                  <View style={{ flex: 1 }}>
                    <Text style={s.mealName}>{m.items.map((i: any) => i.name).join(', ')}</Text>
                    <Text style={s.mealSub}>
                      P {Math.round(m.total_protein_g)}g · C {Math.round(m.total_carbs_g)}g · F {Math.round(m.total_fat_g)}g
                    </Text>
                  </View>
                  <Text style={s.mealCal}>{Math.round(m.total_calories)}</Text>
                  <Pressable onPress={() => deleteMeal(m.id)} style={s.delBtn} testID={`del-meal-${m.id}`}>
                    <Ionicons name="trash-outline" size={16} color={tokens.textMute} />
                  </Pressable>
                </View>
              ))
            )}
          </View>
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: tokens.bg },
  header: { padding: tokens.lg, paddingBottom: tokens.sm },
  title: { color: tokens.text, fontSize: 26, fontWeight: '900', letterSpacing: -0.5 },
  date: { color: tokens.textMute, fontSize: 13, marginTop: 2 },
  body: { padding: tokens.lg, paddingBottom: 140, gap: tokens.md },
  empty: {
    backgroundColor: tokens.bg2,
    borderRadius: tokens.rLg,
    padding: tokens.xl,
    alignItems: 'center',
    gap: tokens.md,
    borderWidth: 1,
    borderColor: tokens.border,
  },
  emptyText: { color: tokens.textDim, textAlign: 'center', fontSize: 14 },
  emptyBtn: {
    flexDirection: 'row',
    gap: 8,
    backgroundColor: tokens.brand,
    paddingHorizontal: 18,
    height: 44,
    borderRadius: 999,
    alignItems: 'center',
  },
  emptyBtnText: { color: tokens.onBrand, fontWeight: '800' },
  group: {
    backgroundColor: tokens.bg2,
    borderRadius: tokens.rLg,
    borderWidth: 1,
    borderColor: tokens.border,
    overflow: 'hidden',
  },
  groupHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: tokens.lg,
    paddingBottom: tokens.md,
  },
  groupHeaderLeft: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  groupTitle: { color: tokens.text, fontSize: 16, fontWeight: '800' },
  groupTotal: { color: tokens.brand, fontSize: 13, fontWeight: '700' },
  groupEmpty: {
    flexDirection: 'row',
    gap: 8,
    padding: tokens.lg,
    paddingTop: 0,
    alignItems: 'center',
  },
  groupEmptyText: { color: tokens.textMute, fontSize: 13 },
  mealRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: tokens.md,
    padding: tokens.lg,
    paddingTop: tokens.sm,
    borderTopWidth: 1,
    borderTopColor: tokens.divider,
  },
  mealName: { color: tokens.text, fontSize: 14, fontWeight: '700' },
  mealSub: { color: tokens.textMute, fontSize: 12, marginTop: 2 },
  mealCal: { color: tokens.text, fontSize: 15, fontWeight: '800' },
  delBtn: { padding: 6 },
});
