import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { api } from '@/src/api';
import { useAuth } from '@/src/auth';
import { t } from '@/src/i18n';
import { macroColors, tokens } from '@/src/theme';

type Ingredient = { name: string; portion_g: number };
type RecItem = {
  id: string;
  kind: 'meal' | 'snack';
  emoji: string;
  name: string;
  description: string;
  prep_minutes: number;
  tags: string[];
  ingredients: Ingredient[];
  calories: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
};

type Focus = 'any' | 'high_protein' | 'low_calorie' | 'vegetarian' | 'vegan' | 'quick';

const FILTERS: { key: Focus; label: string }[] = [
  { key: 'any', label: 'All' },
  { key: 'high_protein', label: 'High-protein' },
  { key: 'low_calorie', label: 'Low-cal' },
  { key: 'vegetarian', label: 'Vegetarian' },
  { key: 'vegan', label: 'Vegan' },
  { key: 'quick', label: 'Quick' },
];

const QUICK_ASKS = [
  'Higher in protein',
  'Under 500 calories',
  'Make it vegetarian',
  'Replace with beef',
  'Faster to prepare',
  'Lower carbs',
];

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

export default function Recommend() {
  const router = useRouter();
  const { user } = useAuth();
  const [remaining, setRemaining] = useState<any>(null);
  const [items, setItems] = useState<RecItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [focus, setFocus] = useState<Focus>('any');
  const [err, setErr] = useState<string | null>(null);
  const [active, setActive] = useState<RecItem | null>(null);

  const sessionIdRef = useRef<string>(`rec-${Math.random().toString(36).slice(2, 8)}`);

  // Premium gate
  useEffect(() => {
    if (user && !user.premium) {
      router.replace('/paywall');
    }
  }, [user, router]);

  const load = useCallback(
    async (f: Focus = focus) => {
      setLoading(true);
      setErr(null);
      try {
        const r = await api.recommend(f, 'all');
        setRemaining(r.remaining);
        setItems(r.items || []);
        sessionIdRef.current = `rec-${Math.random().toString(36).slice(2, 8)}`;
      } catch (e: any) {
        setErr(e.message || 'AI failed');
      } finally {
        setLoading(false);
      }
    },
    [focus],
  );

  useEffect(() => {
    load(focus);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const changeFilter = (f: Focus) => {
    setFocus(f);
    load(f);
  };

  const addToDiary = async (item: RecItem, mealType: 'breakfast' | 'lunch' | 'dinner' | 'snack') => {
    try {
      await api.addMeal({
        meal_type: mealType,
        log_date: todayISO(),
        items: [
          {
            name: item.name,
            portion_g: item.ingredients.reduce((a, i) => a + (i.portion_g || 0), 0) || 100,
            calories: item.calories,
            protein_g: item.protein_g,
            carbs_g: item.carbs_g,
            fat_g: item.fat_g,
            fiber_g: 0,
            sugar_g: 0,
          },
        ],
      });
      router.replace('/(tabs)/diary');
    } catch (e: any) {
      setErr(e.message);
    }
  };

  const applyRefinement = (updated: RecItem) => {
    setItems((prev) => prev.map((x) => (x.id === updated.id ? updated : x)));
    setActive((prev) => (prev && prev.id === updated.id ? updated : prev));
  };

  const meals = useMemo(() => items.filter((i) => i.kind === 'meal'), [items]);
  const snacks = useMemo(() => items.filter((i) => i.kind === 'snack'), [items]);

  return (
    <SafeAreaView style={s.wrap} edges={['top']}>
      <View style={s.header}>
        <Pressable onPress={() => router.back()} style={s.iconBtn} testID="rec-back">
          <Ionicons name="chevron-back" size={22} color={tokens.text} />
        </Pressable>
        <View style={{ flex: 1 }}>
          <Text style={s.title}>{t('completeMyDay')} 🎯</Text>
          <Text style={s.subtitle}>{t('completeMyDaySub')}</Text>
        </View>
        <Pressable onPress={() => load(focus)} style={s.iconBtn} disabled={loading} testID="rec-refresh">
          <Ionicons name={loading ? 'sync' : 'refresh'} size={20} color={tokens.text} />
        </Pressable>
      </View>

      <ScrollView
        contentContainerStyle={s.body}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={() => load(focus)} tintColor={tokens.brand} />}
      >
        {remaining && <RemainingCard remaining={remaining} />}

        <FiltersRow current={focus} onChange={changeFilter} />

        {err && (
          <View style={s.errorCard}>
            <Ionicons name="alert-circle" size={20} color={tokens.danger} />
            <Text style={s.errorText}>{err}</Text>
            <Pressable onPress={() => load(focus)} style={s.retryBtn} testID="rec-retry">
              <Text style={s.retryText}>Try again</Text>
            </Pressable>
          </View>
        )}

        {loading && items.length === 0 && (
          <View style={s.loading} testID="rec-loading">
            <ActivityIndicator size="large" color={tokens.brand} />
            <Text style={s.loadingText}>C1 is planning your day…</Text>
          </View>
        )}

        {meals.length > 0 && (
          <>
            <Text style={s.sectionTitle}>🍽️ {t('meals')}</Text>
            {meals.map((m) => (
              <RecCard
                key={m.id}
                item={m}
                onTalk={() => setActive(m)}
                onAdd={() => addToDiary(m, 'lunch')}
              />
            ))}
          </>
        )}
        {snacks.length > 0 && (
          <>
            <Text style={s.sectionTitle}>🍎 {t('snacks')}</Text>
            {snacks.map((sn) => (
              <RecCard
                key={sn.id}
                item={sn}
                onTalk={() => setActive(sn)}
                onAdd={() => addToDiary(sn, 'snack')}
              />
            ))}
          </>
        )}

        {!loading && items.length === 0 && !err && (
          <Text style={s.emptyText}>Tap refresh to get suggestions.</Text>
        )}

        <Text style={s.foot}>
          Estimates by AI. Adjust portions in the diary as needed.
        </Text>
      </ScrollView>

      <RefineSheet
        item={active}
        sessionId={sessionIdRef.current}
        onClose={() => setActive(null)}
        onUpdated={applyRefinement}
        onAdd={(it) => {
          setActive(null);
          addToDiary(it, it.kind === 'snack' ? 'snack' : 'lunch');
        }}
      />
    </SafeAreaView>
  );
}

function RemainingCard({ remaining }: { remaining: any }) {
  const done =
    remaining.calories <= 0 &&
    remaining.protein_g <= 0 &&
    remaining.carbs_g <= 0 &&
    remaining.fat_g <= 0;
  return (
    <View style={s.remainCard} testID="rec-remaining">
      <View style={s.remainHeader}>
        <Ionicons name="flag" size={16} color={tokens.brand} />
        <Text style={s.remainTitle}>{t('remainingToday')}</Text>
      </View>
      <View style={s.remainRow}>
        <RemainStat label="kcal" value={remaining.calories} color={tokens.brand} />
        <RemainStat label="P" value={`${remaining.protein_g}g`} color={macroColors.protein} />
        <RemainStat label="C" value={`${remaining.carbs_g}g`} color={macroColors.carbs} />
        <RemainStat label="F" value={`${remaining.fat_g}g`} color={macroColors.fat} />
      </View>
      {done && (
        <View style={s.doneBadge}>
          <Ionicons name="checkmark-circle" size={14} color={tokens.success} />
          <Text style={s.doneText}>{t('goalHit')}</Text>
        </View>
      )}
    </View>
  );
}

function RemainStat({ label, value, color }: { label: string; value: any; color: string }) {
  return (
    <View style={s.remainStat}>
      <Text style={[s.remainVal, { color }]}>{value}</Text>
      <Text style={s.remainLbl}>{label}</Text>
    </View>
  );
}

function FiltersRow({ current, onChange }: { current: Focus; onChange: (f: Focus) => void }) {
  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={s.filtersRow}
    >
      {FILTERS.map((f) => (
        <Pressable
          key={f.key}
          onPress={() => onChange(f.key)}
          style={[s.filterChip, current === f.key && s.filterChipActive]}
          testID={`rec-filter-${f.key}`}
        >
          <Text style={[s.filterText, current === f.key && s.filterTextActive]}>{f.label}</Text>
        </Pressable>
      ))}
    </ScrollView>
  );
}

function RecCard({
  item,
  onTalk,
  onAdd,
}: {
  item: RecItem;
  onTalk: () => void;
  onAdd: () => void;
}) {
  return (
    <View style={s.card} testID={`rec-card-${item.id}`}>
      <View style={s.cardHead}>
        <Text style={s.cardEmoji}>{item.emoji}</Text>
        <View style={{ flex: 1 }}>
          <Text style={s.cardName}>{item.name}</Text>
          <Text style={s.cardDesc} numberOfLines={2}>
            {item.description}
          </Text>
          <View style={s.tagsRow}>
            <View style={s.prepBadge}>
              <Ionicons name="time-outline" size={11} color={tokens.textDim} />
              <Text style={s.prepText}>{item.prep_minutes}m</Text>
            </View>
            {item.tags.slice(0, 3).map((tg, i) => (
              <View key={i} style={s.tagChip}>
                <Text style={s.tagText}>{tg}</Text>
              </View>
            ))}
          </View>
        </View>
      </View>

      <View style={s.macrosGrid}>
        <MacroCell label="kcal" val={Math.round(item.calories)} color={tokens.brand} big />
        <MacroCell label="P" val={`${Math.round(item.protein_g)}g`} color={macroColors.protein} />
        <MacroCell label="C" val={`${Math.round(item.carbs_g)}g`} color={macroColors.carbs} />
        <MacroCell label="F" val={`${Math.round(item.fat_g)}g`} color={macroColors.fat} />
      </View>

      {item.ingredients.length > 0 && (
        <View style={s.ingRow}>
          <Text style={s.ingLabel}>Ingredients: </Text>
          <Text style={s.ingText} numberOfLines={2}>
            {item.ingredients.map((i) => `${i.name} ${Math.round(i.portion_g)}g`).join(' · ')}
          </Text>
        </View>
      )}

      <View style={s.cardActions}>
        <Pressable
          style={s.talkBtn}
          onPress={onTalk}
          testID={`rec-talk-${item.id}`}
        >
          <Ionicons name="sparkles" size={14} color={tokens.brand} />
          <Text style={s.talkText}>{t('talkToC1')}</Text>
        </Pressable>
        <Pressable style={s.addBtn} onPress={onAdd} testID={`rec-add-${item.id}`}>
          <Ionicons name="add" size={16} color={tokens.onBrand} />
          <Text style={s.addText}>Add</Text>
        </Pressable>
      </View>
    </View>
  );
}

function MacroCell({ label, val, color, big }: any) {
  return (
    <View style={s.macroCell}>
      <Text style={[s.macroVal, big && { fontSize: 20 }, { color }]}>{val}</Text>
      <Text style={s.macroLbl}>{label}</Text>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Refine bottom sheet
// ---------------------------------------------------------------------------
function RefineSheet({
  item,
  sessionId,
  onClose,
  onUpdated,
  onAdd,
}: {
  item: RecItem | null;
  sessionId: string;
  onClose: () => void;
  onUpdated: (it: RecItem) => void;
  onAdd: (it: RecItem) => void;
}) {
  const [current, setCurrent] = useState<RecItem | null>(item);
  const [history, setHistory] = useState<{ role: 'user' | 'assistant'; text: string }[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const listRef = useRef<FlatList>(null);

  // reset when a different item becomes active
  useEffect(() => {
    setCurrent(item);
    setHistory([]);
    setInput('');
    setErr(null);
  }, [item?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const submit = async (text?: string) => {
    const req = (text ?? input).trim();
    if (!req || !current || sending) return;
    setSending(true);
    setErr(null);
    setInput('');
    setHistory((h) => [...h, { role: 'user', text: req }]);
    try {
      const updated: RecItem = await api.refineRecommendation(sessionId, current, req);
      setCurrent(updated);
      onUpdated(updated);
      setHistory((h) => [
        ...h,
        { role: 'assistant', text: `Updated → ${updated.name} · ${Math.round(updated.calories)} kcal · P${Math.round(updated.protein_g)}g / C${Math.round(updated.carbs_g)}g / F${Math.round(updated.fat_g)}g` },
      ]);
      setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 100);
    } catch (e: any) {
      setErr(e.message || 'AI failed');
    } finally {
      setSending(false);
    }
  };

  return (
    <Modal visible={!!item} animationType="slide" transparent onRequestClose={onClose}>
      <View style={s.sheetBackdrop}>
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
          style={s.sheet}
        >
          <View style={s.sheetHandle} />
          {current && (
            <>
              <View style={s.sheetHeader}>
                <Text style={s.sheetEmoji}>{current.emoji}</Text>
                <View style={{ flex: 1 }}>
                  <Text style={s.sheetName} numberOfLines={1}>
                    {current.name}
                  </Text>
                  <Text style={s.sheetMacros}>
                    {Math.round(current.calories)} kcal · P{Math.round(current.protein_g)}g / C
                    {Math.round(current.carbs_g)}g / F{Math.round(current.fat_g)}g
                  </Text>
                </View>
                <Pressable onPress={onClose} style={s.iconBtn} testID="refine-close">
                  <Ionicons name="close" size={22} color={tokens.text} />
                </Pressable>
              </View>

              <FlatList
                ref={listRef}
                data={history}
                keyExtractor={(_, i) => String(i)}
                contentContainerStyle={s.sheetBody}
                ListHeaderComponent={
                  <View>
                    <Text style={s.sheetHint}>
                      Ask C1 to modify this {current.kind}. Macros will update in real time.
                    </Text>
                    <View style={s.quickAsks}>
                      {QUICK_ASKS.map((q, i) => (
                        <Pressable
                          key={i}
                          onPress={() => submit(q)}
                          style={s.quickAsk}
                          disabled={sending}
                          testID={`refine-quick-${i}`}
                        >
                          <Text style={s.quickAskText}>{q}</Text>
                        </Pressable>
                      ))}
                    </View>
                  </View>
                }
                renderItem={({ item: m }) => (
                  <View
                    style={[
                      s.msgWrap,
                      { justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start' },
                    ]}
                  >
                    <View style={[s.msg, m.role === 'user' ? s.msgUser : s.msgAi]}>
                      <Text
                        style={{
                          color: m.role === 'user' ? tokens.onBrand : tokens.text,
                          fontSize: 14,
                        }}
                      >
                        {m.text}
                      </Text>
                    </View>
                  </View>
                )}
              />

              {sending && (
                <View style={s.typing}>
                  <ActivityIndicator size="small" color={tokens.brand} />
                  <Text style={s.typingText}>C1 is adjusting…</Text>
                </View>
              )}
              {err && <Text style={{ color: tokens.danger, paddingHorizontal: 16 }}>{err}</Text>}

              <View style={s.inputBar}>
                <TextInput
                  testID="refine-input"
                  value={input}
                  onChangeText={setInput}
                  placeholder={t('askModification')}
                  placeholderTextColor={tokens.textMute}
                  style={s.input}
                  onSubmitEditing={() => submit()}
                />
                <Pressable
                  testID="refine-send"
                  onPress={() => submit()}
                  disabled={!input.trim() || sending}
                  style={[s.sendBtn, (!input.trim() || sending) && { opacity: 0.4 }]}
                >
                  <Ionicons name="send" size={16} color={tokens.onBrand} />
                </Pressable>
              </View>
              <Pressable style={s.addToDiaryBtn} onPress={() => onAdd(current)} testID="refine-add">
                <Ionicons name="checkmark" size={16} color={tokens.onBrand} />
                <Text style={s.addToDiaryText}>Add to diary</Text>
              </Pressable>
            </>
          )}
        </KeyboardAvoidingView>
      </View>
    </Modal>
  );
}

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: tokens.bg },
  header: {
    padding: tokens.md,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  iconBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: tokens.bg2,
    borderWidth: 1,
    borderColor: tokens.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: { color: tokens.text, fontSize: 20, fontWeight: '900', letterSpacing: -0.5 },
  subtitle: { color: tokens.textMute, fontSize: 12 },
  body: { padding: tokens.lg, paddingBottom: 120, gap: tokens.md },
  remainCard: {
    backgroundColor: tokens.brandTint,
    borderRadius: tokens.rLg,
    padding: tokens.lg,
    borderWidth: 1,
    borderColor: tokens.brand,
  },
  remainHeader: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 10 },
  remainTitle: { color: tokens.brand, fontSize: 12, fontWeight: '800', letterSpacing: 1, textTransform: 'uppercase' },
  remainRow: { flexDirection: 'row', justifyContent: 'space-between' },
  remainStat: { alignItems: 'center' },
  remainVal: { fontSize: 22, fontWeight: '900', letterSpacing: -0.5 },
  remainLbl: { color: tokens.textMute, fontSize: 11, marginTop: 2, fontWeight: '600' },
  doneBadge: {
    marginTop: 10,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    alignSelf: 'flex-start',
    backgroundColor: 'rgba(52,211,153,0.15)',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 999,
  },
  doneText: { color: tokens.success, fontSize: 11, fontWeight: '800' },
  filtersRow: { gap: 8, paddingRight: 8 },
  filterChip: {
    paddingHorizontal: 14,
    height: 36,
    borderRadius: 999,
    backgroundColor: tokens.bg2,
    borderWidth: 1,
    borderColor: tokens.border,
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  filterChipActive: { backgroundColor: tokens.brandTint, borderColor: tokens.brand },
  filterText: { color: tokens.textDim, fontSize: 13, fontWeight: '600' },
  filterTextActive: { color: tokens.brand, fontWeight: '800' },
  sectionTitle: {
    color: tokens.text,
    fontSize: 16,
    fontWeight: '800',
    marginTop: tokens.sm,
  },
  card: {
    backgroundColor: tokens.bg2,
    borderRadius: tokens.rLg,
    padding: tokens.md,
    borderWidth: 1,
    borderColor: tokens.border,
    gap: 10,
  },
  cardHead: { flexDirection: 'row', gap: 12, alignItems: 'flex-start' },
  cardEmoji: { fontSize: 36, marginTop: 2 },
  cardName: { color: tokens.text, fontSize: 16, fontWeight: '800' },
  cardDesc: { color: tokens.textMute, fontSize: 12, marginTop: 2, lineHeight: 16 },
  tagsRow: { flexDirection: 'row', gap: 6, marginTop: 6, flexWrap: 'wrap' },
  prepBadge: {
    flexDirection: 'row',
    gap: 3,
    alignItems: 'center',
    backgroundColor: tokens.bg3,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 999,
  },
  prepText: { color: tokens.textDim, fontSize: 10, fontWeight: '700' },
  tagChip: {
    backgroundColor: tokens.bg3,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 999,
  },
  tagText: { color: tokens.textDim, fontSize: 10, fontWeight: '600' },
  macrosGrid: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    backgroundColor: tokens.bg3,
    borderRadius: tokens.rMd,
    padding: 10,
  },
  macroCell: { alignItems: 'center', flex: 1 },
  macroVal: { fontSize: 14, fontWeight: '800' },
  macroLbl: { color: tokens.textMute, fontSize: 10, marginTop: 2, fontWeight: '600' },
  ingRow: { flexDirection: 'row', flexWrap: 'wrap' },
  ingLabel: { color: tokens.textDim, fontSize: 11, fontWeight: '700' },
  ingText: { color: tokens.textMute, fontSize: 11, flex: 1, lineHeight: 16 },
  cardActions: { flexDirection: 'row', gap: 8 },
  talkBtn: {
    flex: 1,
    flexDirection: 'row',
    gap: 6,
    alignItems: 'center',
    justifyContent: 'center',
    height: 40,
    borderRadius: 999,
    backgroundColor: tokens.brandTint,
    borderWidth: 1,
    borderColor: tokens.brand,
  },
  talkText: { color: tokens.brand, fontWeight: '800', fontSize: 13 },
  addBtn: {
    width: 88,
    flexDirection: 'row',
    gap: 4,
    alignItems: 'center',
    justifyContent: 'center',
    height: 40,
    borderRadius: 999,
    backgroundColor: tokens.brand,
  },
  addText: { color: tokens.onBrand, fontWeight: '800', fontSize: 13 },
  loading: {
    padding: tokens.xl,
    alignItems: 'center',
    gap: 10,
  },
  loadingText: { color: tokens.textDim, fontSize: 13 },
  errorCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    padding: tokens.md,
    backgroundColor: tokens.bg2,
    borderRadius: tokens.rMd,
    borderWidth: 1,
    borderColor: tokens.border,
  },
  errorText: { color: tokens.textDim, fontSize: 12, flex: 1 },
  retryBtn: { backgroundColor: tokens.brand, paddingHorizontal: 12, height: 32, borderRadius: 999, justifyContent: 'center' },
  retryText: { color: tokens.onBrand, fontWeight: '800', fontSize: 12 },
  emptyText: { color: tokens.textMute, fontSize: 13, textAlign: 'center', padding: 24 },
  foot: { color: tokens.textMute, fontSize: 11, textAlign: 'center', marginTop: 8, lineHeight: 16 },

  // sheet
  sheetBackdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.6)', justifyContent: 'flex-end' },
  sheet: {
    backgroundColor: tokens.bg2,
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    maxHeight: '90%',
    minHeight: '60%',
    paddingBottom: tokens.lg,
  },
  sheetHandle: {
    width: 40,
    height: 4,
    borderRadius: 2,
    backgroundColor: tokens.borderStrong,
    alignSelf: 'center',
    marginTop: 8,
    marginBottom: 4,
  },
  sheetHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    padding: tokens.md,
    borderBottomWidth: 1,
    borderBottomColor: tokens.divider,
  },
  sheetEmoji: { fontSize: 32 },
  sheetName: { color: tokens.text, fontSize: 16, fontWeight: '800' },
  sheetMacros: { color: tokens.textDim, fontSize: 12, marginTop: 2 },
  sheetBody: { padding: tokens.md, gap: 6 },
  sheetHint: { color: tokens.textMute, fontSize: 12, marginBottom: 10, lineHeight: 16 },
  quickAsks: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 6 },
  quickAsk: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 999,
    backgroundColor: tokens.bg3,
    borderWidth: 1,
    borderColor: tokens.border,
  },
  quickAskText: { color: tokens.textDim, fontSize: 12, fontWeight: '600' },
  msgWrap: { flexDirection: 'row', marginVertical: 3 },
  msg: { maxWidth: '85%', paddingHorizontal: 12, paddingVertical: 8, borderRadius: 14 },
  msgUser: { backgroundColor: tokens.brand, borderBottomRightRadius: 4 },
  msgAi: { backgroundColor: tokens.bg3, borderBottomLeftRadius: 4 },
  typing: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 16, paddingVertical: 4 },
  typingText: { color: tokens.textMute, fontSize: 12 },
  inputBar: {
    flexDirection: 'row',
    padding: tokens.md,
    paddingTop: 6,
    gap: 8,
    alignItems: 'center',
  },
  input: {
    flex: 1,
    minHeight: 44,
    backgroundColor: tokens.bg3,
    borderRadius: 22,
    paddingHorizontal: 14,
    color: tokens.text,
    fontSize: 14,
  },
  sendBtn: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: tokens.brand,
    alignItems: 'center',
    justifyContent: 'center',
  },
  addToDiaryBtn: {
    marginHorizontal: tokens.md,
    height: 48,
    borderRadius: 999,
    backgroundColor: tokens.brand,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 6,
  },
  addToDiaryText: { color: tokens.onBrand, fontWeight: '800', fontSize: 14 },
});
