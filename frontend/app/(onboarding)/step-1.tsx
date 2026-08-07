import { useRouter } from 'expo-router';
import { useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { tokens } from '@/src/theme';
import { t } from '@/src/i18n';
import { api } from '@/src/api';
import { useAuth } from '@/src/auth';

type Draft = {
  step: number;
  age?: number;
  gender?: 'male' | 'female' | 'other';
  height_cm?: number;
  weight_kg?: number;
  target_weight_kg?: number;
  activity?: 'sedentary' | 'light' | 'moderate' | 'active' | 'very_active';
  goal?: 'lose' | 'maintain' | 'gain';
};

const TOTAL = 5;

export default function Onboarding() {
  const router = useRouter();
  const { refresh } = useAuth();
  const [d, setD] = useState<Draft>({ step: 1 });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const canNext = (): boolean => {
    switch (d.step) {
      case 1:
        return !!d.gender && !!d.age && d.age > 10 && d.age < 120;
      case 2:
        return !!d.height_cm && d.height_cm > 80 && d.height_cm < 250;
      case 3:
        return !!d.weight_kg && d.weight_kg > 25 && !!d.target_weight_kg && d.target_weight_kg > 25;
      case 4:
        return !!d.activity;
      case 5:
        return !!d.goal;
    }
    return false;
  };

  const next = async () => {
    if (!canNext()) return;
    if (d.step < TOTAL) {
      setD({ ...d, step: d.step + 1 });
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await api.updateProfile({
        age: d.age,
        gender: d.gender,
        height_cm: d.height_cm,
        weight_kg: d.weight_kg,
        target_weight_kg: d.target_weight_kg,
        activity: d.activity,
        goal: d.goal,
      });
      await refresh();
      router.replace('/(tabs)');
    } catch (e: any) {
      setErr(e.message || 'Error');
    } finally {
      setBusy(false);
    }
  };

  return (
    <SafeAreaView style={s.wrap} edges={['top', 'bottom']}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={{ flex: 1 }}
      >
        <View style={s.header}>
          <View style={s.progressWrap}>
            {Array.from({ length: TOTAL }).map((_, i) => (
              <View
                key={i}
                style={[
                  s.progressDot,
                  i < d.step && { backgroundColor: tokens.brand },
                ]}
              />
            ))}
          </View>
          <Text style={s.title}>{t('onbTitle')}</Text>
          <Text style={s.sub}>{t('onbSub')}</Text>
        </View>

        <ScrollView contentContainerStyle={s.body} keyboardShouldPersistTaps="handled">
          {d.step === 1 && (
            <>
              <Label>{t('gender')}</Label>
              <Row>
                {(['male', 'female', 'other'] as const).map((g) => (
                  <Chip
                    key={g}
                    active={d.gender === g}
                    onPress={() => setD({ ...d, gender: g })}
                    testID={`onb-gender-${g}`}
                  >
                    {t(g)}
                  </Chip>
                ))}
              </Row>
              <Label>{t('age')}</Label>
              <NumberInput
                testID="onb-age"
                value={d.age}
                onChange={(n) => setD({ ...d, age: n })}
                placeholder="30"
              />
            </>
          )}
          {d.step === 2 && (
            <>
              <Label>{t('height')}</Label>
              <NumberInput
                testID="onb-height"
                value={d.height_cm}
                onChange={(n) => setD({ ...d, height_cm: n })}
                placeholder="175"
              />
            </>
          )}
          {d.step === 3 && (
            <>
              <Label>{t('weight')}</Label>
              <NumberInput
                testID="onb-weight"
                value={d.weight_kg}
                onChange={(n) => setD({ ...d, weight_kg: n })}
                placeholder="72"
              />
              <Label>{t('targetWeight')}</Label>
              <NumberInput
                testID="onb-target-weight"
                value={d.target_weight_kg}
                onChange={(n) => setD({ ...d, target_weight_kg: n })}
                placeholder="68"
              />
            </>
          )}
          {d.step === 4 && (
            <>
              <Label>{t('activity')}</Label>
              <View style={{ gap: tokens.sm }}>
                {(['sedentary', 'light', 'moderate', 'active', 'very_active'] as const).map(
                  (a) => (
                    <Pressable
                      key={a}
                      testID={`onb-activity-${a}`}
                      onPress={() => setD({ ...d, activity: a })}
                      style={[s.card, d.activity === a && s.cardActive]}
                    >
                      <Text style={[s.cardText, d.activity === a && { color: tokens.brand }]}>
                        {t(a)}
                      </Text>
                    </Pressable>
                  )
                )}
              </View>
            </>
          )}
          {d.step === 5 && (
            <>
              <Label>{t('goal')}</Label>
              <View style={{ gap: tokens.sm }}>
                {(['lose', 'maintain', 'gain'] as const).map((g) => (
                  <Pressable
                    key={g}
                    testID={`onb-goal-${g}`}
                    onPress={() => setD({ ...d, goal: g })}
                    style={[s.card, d.goal === g && s.cardActive]}
                  >
                    <Text style={[s.cardText, d.goal === g && { color: tokens.brand }]}>
                      {t(g)}
                    </Text>
                  </Pressable>
                ))}
              </View>
            </>
          )}
          {err && <Text style={{ color: tokens.danger, marginTop: 12 }}>{err}</Text>}
        </ScrollView>

        <View style={s.footer}>
          <Pressable
            testID="onb-next"
            disabled={!canNext() || busy}
            onPress={next}
            style={[s.btn, (!canNext() || busy) && { opacity: 0.4 }]}
          >
            <Text style={s.btnText}>{d.step === TOTAL ? t('finish') : t('next')}</Text>
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function Label({ children }: { children: any }) {
  return <Text style={s.label}>{children}</Text>;
}
function Row({ children }: { children: any }) {
  return <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: tokens.sm }}>{children}</View>;
}
function Chip({
  active,
  onPress,
  testID,
  children,
}: {
  active?: boolean;
  onPress: () => void;
  testID?: string;
  children: any;
}) {
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      style={[s.chip, active && { backgroundColor: tokens.brandTint, borderColor: tokens.brand }]}
    >
      <Text style={[s.chipText, active && { color: tokens.brand, fontWeight: '800' }]}>{children}</Text>
    </Pressable>
  );
}
function NumberInput({
  value,
  onChange,
  placeholder,
  testID,
}: {
  value?: number;
  onChange: (n: number | undefined) => void;
  placeholder?: string;
  testID?: string;
}) {
  return (
    <TextInput
      testID={testID}
      keyboardType="numeric"
      placeholder={placeholder}
      placeholderTextColor={tokens.textMute}
      value={value !== undefined ? String(value) : ''}
      onChangeText={(txt) => {
        const n = parseFloat(txt.replace(',', '.'));
        onChange(isNaN(n) ? undefined : n);
      }}
      style={s.input}
    />
  );
}

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: tokens.bg },
  header: { padding: tokens.xl, paddingTop: tokens.md, gap: tokens.md },
  progressWrap: { flexDirection: 'row', gap: 6 },
  progressDot: { flex: 1, height: 4, borderRadius: 999, backgroundColor: tokens.bg3 },
  title: { color: tokens.text, fontSize: 26, fontWeight: '900', letterSpacing: -0.5 },
  sub: { color: tokens.textMute, fontSize: 14 },
  body: { padding: tokens.xl, paddingTop: 0, gap: tokens.md, paddingBottom: 40 },
  label: { color: tokens.textDim, fontSize: 13, fontWeight: '700', letterSpacing: 0.5, textTransform: 'uppercase', marginTop: tokens.md },
  input: {
    backgroundColor: tokens.bg2,
    color: tokens.text,
    borderRadius: tokens.rLg,
    paddingHorizontal: 16,
    height: 56,
    fontSize: 20,
    fontWeight: '700',
    borderWidth: 1,
    borderColor: tokens.border,
  },
  chip: {
    paddingHorizontal: 18,
    height: 44,
    borderRadius: 999,
    backgroundColor: tokens.bg2,
    borderWidth: 1,
    borderColor: tokens.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  chipText: { color: tokens.textDim, fontSize: 14, fontWeight: '600' },
  card: {
    backgroundColor: tokens.bg2,
    borderRadius: tokens.rLg,
    padding: tokens.lg,
    borderWidth: 1,
    borderColor: tokens.border,
  },
  cardActive: { borderColor: tokens.brand, backgroundColor: tokens.brandTint },
  cardText: { color: tokens.text, fontSize: 16, fontWeight: '700' },
  footer: { padding: tokens.xl, paddingTop: tokens.sm },
  btn: {
    backgroundColor: tokens.brand,
    height: 56,
    borderRadius: tokens.rLg,
    alignItems: 'center',
    justifyContent: 'center',
  },
  btnText: { color: tokens.onBrand, fontSize: 16, fontWeight: '800' },
});
