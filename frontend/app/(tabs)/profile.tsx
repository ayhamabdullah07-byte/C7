import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { Modal, Pressable, ScrollView, StyleSheet, Switch, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { api } from '@/src/api';
import { useAuth } from '@/src/auth';
import { LANGUAGES, currentLang, setLang, t } from '@/src/i18n';
import * as notif from '@/src/notifications';
import { tokens } from '@/src/theme';

export default function Profile() {
  const router = useRouter();
  const { user, signOut, refresh } = useAuth();
  const [langOpen, setLangOpen] = useState(false);
  const [lang, setL] = useState(currentLang());
  const [quota, setQuota] = useState<any>(null);
  const [notifOn, setNotifOn] = useState(false);
  const [notifBusy, setNotifBusy] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const q = await api.scanQuota();
        setQuota(q);
      } catch {}
      setNotifOn(await notif.isEnabled());
    })();
  }, [user?.plan]);

  const chooseLang = async (code: string) => {
    await setLang(code);
    setL(code);
    setLangOpen(false);
    // refresh so texts re-render
    setTimeout(() => refresh(), 100);
  };

  const togglePremium = async () => {
    try {
      await api.togglePremium();
      await refresh();
    } catch {}
  };

  const toggleNotifications = async (v: boolean) => {
    setNotifBusy(true);
    try {
      if (v) {
        const ok = await notif.enableForPlus(user?.name);
        setNotifOn(ok);
      } else {
        await notif.disable();
        setNotifOn(false);
      }
    } catch {
      setNotifOn(false);
    } finally {
      setNotifBusy(false);
    }
  };

  const deleteAcc = async () => {
    try {
      await api.deleteAccount();
      await signOut();
      router.replace('/(auth)/welcome');
    } catch {}
  };

  const targets = user?.targets;
  const plan: 'free' | 'premium' | 'plus' = user?.plan || 'free';
  const planLabel = plan === 'plus' ? 'C1 Plus' : plan === 'premium' ? 'C1 Premium' : 'Free';

  return (
    <SafeAreaView style={s.wrap} edges={['top']}>
      <ScrollView contentContainerStyle={s.body}>
        <View style={s.head}>
          <View style={s.avatarBig}>
            <Text style={s.avatarText}>{(user?.name || 'C')[0]?.toUpperCase()}</Text>
          </View>
          <Text style={s.name} testID="profile-name">{user?.name}</Text>
          <Text style={s.email}>{user?.email}</Text>
          <View style={[s.premiumBadge, plan === 'free' && s.freeBadge]} testID="plan-badge">
            {plan !== 'free' && <Ionicons name="star" size={12} color={tokens.onBrand} />}
            <Text style={[s.premiumText, plan === 'free' && { color: tokens.textDim }]}>{planLabel}</Text>
          </View>
        </View>

        {quota && (
          <View style={s.card} testID="scan-quota-card">
            <Text style={s.cardTitle}>Scans (last 24h)</Text>
            <View style={s.quotaRow}>
              <Text style={s.quotaUsed}>
                {quota.used}
                <Text style={s.quotaMax}> / {quota.limit === null ? '∞' : quota.limit}</Text>
              </Text>
              <Text style={s.quotaSub}>
                {quota.blocked
                  ? 'Daily limit reached'
                  : quota.remaining === null
                  ? 'Unlimited (fair-use)'
                  : `${quota.remaining} remaining`}
              </Text>
            </View>
          </View>
        )}

        {targets && (
          <View style={s.card}>
            <Text style={s.cardTitle}>Your daily targets</Text>
            <View style={s.grid}>
              <Stat label="Calories" val={`${targets.calories}`} unit="kcal" />
              <Stat label="Protein" val={`${targets.protein_g}`} unit="g" />
              <Stat label="Carbs" val={`${targets.carbs_g}`} unit="g" />
              <Stat label="Fat" val={`${targets.fat_g}`} unit="g" />
              <Stat label="Water" val={`${targets.water_ml}`} unit="ml" />
              <Stat label="TDEE" val={`${targets.tdee}`} unit="kcal" />
            </View>
          </View>
        )}

        <Pressable
          onPress={() => router.push('/paywall')}
          style={[s.card, s.premiumCard]}
          testID="premium-card"
        >
          <View style={{ flex: 1 }}>
            <Text style={s.premiumTitle}>{user?.premium ? t('managePremium') : t('goPremium')}</Text>
            <Text style={s.premiumSub}>
              {user?.premium ? t('premiumActive') : `${t('intro')} · ${t('standard')}`}
            </Text>
          </View>
          <Ionicons name="star" size={22} color={tokens.brand} />
        </Pressable>

        <View style={s.card}>
          <Row
            testID="profile-lang"
            icon="language"
            label={t('language')}
            value={LANGUAGES.find((l) => l.code === lang)?.label || 'English'}
            onPress={() => setLangOpen(true)}
          />
          <Row
            testID="profile-toggle-premium"
            icon="star-outline"
            label={`Change plan (stub) — ${planLabel}`}
            value=""
            onPress={togglePremium}
          />
          {plan === 'plus' && (
            <View style={s.rowLike} testID="profile-notifications-row">
              <Ionicons name="notifications-outline" size={18} color={tokens.textDim} />
              <View style={{ flex: 1 }}>
                <Text style={s.rowLabel}>Daily reminders</Text>
                <Text style={s.rowHint}>Lunch nudge at 11:00 · evening at 19:00</Text>
              </View>
              <Switch
                testID="profile-notifications-switch"
                value={notifOn}
                onValueChange={toggleNotifications}
                disabled={notifBusy}
                trackColor={{ true: tokens.brand, false: tokens.bg3 }}
                thumbColor={notifOn ? tokens.onBrand : tokens.textMute}
              />
            </View>
          )}
          <Row
            testID="profile-signout"
            icon="log-out-outline"
            label={t('logout')}
            value=""
            onPress={async () => {
              await signOut();
              router.replace('/(auth)/welcome');
            }}
          />
          <Row
            testID="profile-delete"
            icon="trash-outline"
            label={t('deleteAccount')}
            value=""
            danger
            onPress={deleteAcc}
          />
        </View>

        <Text style={s.foot}>{t('medicalDisclaimer')}</Text>
        <Text style={s.foot}>C1 v1.0 · Made with care</Text>
      </ScrollView>

      <Modal visible={langOpen} animationType="slide" transparent>
        <Pressable style={s.modalBackdrop} onPress={() => setLangOpen(false)}>
          <View style={s.sheet}>
            <Text style={s.sheetTitle}>{t('language')}</Text>
            {LANGUAGES.map((L) => (
              <Pressable
                key={L.code}
                style={[s.langRow, L.code === lang && { backgroundColor: tokens.brandTint }]}
                onPress={() => chooseLang(L.code)}
                testID={`lang-${L.code}`}
              >
                <Text style={[s.langLabel, L.code === lang && { color: tokens.brand }]}>
                  {L.label}
                </Text>
                {L.code === lang && <Ionicons name="checkmark" size={18} color={tokens.brand} />}
              </Pressable>
            ))}
          </View>
        </Pressable>
      </Modal>
    </SafeAreaView>
  );
}

function Stat({ label, val, unit }: { label: string; val: string; unit: string }) {
  return (
    <View style={s.stat}>
      <Text style={s.statVal}>
        {val}<Text style={s.statUnit}> {unit}</Text>
      </Text>
      <Text style={s.statLabel}>{label}</Text>
    </View>
  );
}

function Row({
  icon,
  label,
  value,
  onPress,
  danger,
  testID,
}: {
  icon: any;
  label: string;
  value?: string;
  onPress?: () => void;
  danger?: boolean;
  testID?: string;
}) {
  return (
    <Pressable style={s.row} onPress={onPress} testID={testID}>
      <Ionicons name={icon} size={18} color={danger ? tokens.danger : tokens.textDim} />
      <Text style={[s.rowLabel, danger && { color: tokens.danger }]}>{label}</Text>
      {value ? <Text style={s.rowVal}>{value}</Text> : null}
      <Ionicons name="chevron-forward" size={16} color={tokens.textMute} />
    </Pressable>
  );
}

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: tokens.bg },
  body: { padding: tokens.lg, paddingBottom: 140, gap: tokens.md },
  head: { alignItems: 'center', gap: 6, marginBottom: tokens.md },
  avatarBig: {
    width: 84,
    height: 84,
    borderRadius: 28,
    backgroundColor: tokens.brand,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 6,
  },
  avatarText: { color: tokens.onBrand, fontSize: 34, fontWeight: '900' },
  name: { color: tokens.text, fontSize: 22, fontWeight: '800' },
  email: { color: tokens.textMute, fontSize: 13 },
  premiumBadge: {
    flexDirection: 'row', gap: 4, alignItems: 'center',
    backgroundColor: tokens.brand, paddingHorizontal: 10, height: 24, borderRadius: 999, marginTop: 6,
  },
  freeBadge: { backgroundColor: tokens.bg3, borderWidth: 1, borderColor: tokens.border },
  premiumText: { color: tokens.onBrand, fontWeight: '800', fontSize: 11 },
  quotaRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-end', padding: 10, paddingTop: 4 },
  quotaUsed: { color: tokens.text, fontSize: 26, fontWeight: '900', letterSpacing: -0.5 },
  quotaMax: { color: tokens.textMute, fontSize: 14, fontWeight: '600' },
  quotaSub: { color: tokens.textDim, fontSize: 12 },
  rowLike: {
    flexDirection: 'row', alignItems: 'center', gap: tokens.md,
    padding: tokens.md, borderBottomWidth: 1, borderBottomColor: tokens.divider,
  },
  rowHint: { color: tokens.textMute, fontSize: 11, marginTop: 2 },
  card: {
    backgroundColor: tokens.bg2,
    borderRadius: tokens.rLg,
    borderWidth: 1,
    borderColor: tokens.border,
    padding: tokens.md,
  },
  cardTitle: { color: tokens.textDim, fontSize: 12, fontWeight: '700', letterSpacing: 0.5, textTransform: 'uppercase', padding: 6 },
  grid: { flexDirection: 'row', flexWrap: 'wrap' },
  stat: { width: '33.33%', padding: 10 },
  statVal: { color: tokens.text, fontSize: 18, fontWeight: '800' },
  statUnit: { color: tokens.textMute, fontSize: 11, fontWeight: '600' },
  statLabel: { color: tokens.textMute, fontSize: 11, marginTop: 2 },
  premiumCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    padding: tokens.lg,
    borderColor: tokens.brand,
  },
  premiumTitle: { color: tokens.text, fontSize: 16, fontWeight: '800' },
  premiumSub: { color: tokens.textDim, fontSize: 12, marginTop: 2 },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: tokens.md,
    padding: tokens.md,
    borderBottomWidth: 1,
    borderBottomColor: tokens.divider,
  },
  rowLabel: { color: tokens.text, fontSize: 14, fontWeight: '600', flex: 1 },
  rowVal: { color: tokens.textMute, fontSize: 13 },
  foot: { color: tokens.textMute, fontSize: 11, textAlign: 'center', marginTop: 8, lineHeight: 16 },
  modalBackdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.6)',
    justifyContent: 'flex-end',
  },
  sheet: {
    backgroundColor: tokens.bg2,
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    padding: tokens.lg,
    paddingBottom: tokens.xxl,
    gap: 6,
  },
  sheetTitle: { color: tokens.text, fontSize: 18, fontWeight: '800', marginBottom: 8 },
  langRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 14,
    borderRadius: 12,
  },
  langLabel: { color: tokens.text, fontSize: 15, fontWeight: '600' },
});
