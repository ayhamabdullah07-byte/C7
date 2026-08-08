import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { tokens } from '@/src/theme';
import { t } from '@/src/i18n';
import { useAuth } from '@/src/auth';

export default function Login() {
  const router = useRouter();
  const { signIn } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setErr(null);
    setBusy(true);
    try {
      await signIn(email.trim().toLowerCase(), password);
      router.replace('/');
    } catch (e: any) {
      setErr(e.message || t('errors'));
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
        <Pressable onPress={() => router.back()} style={s.back} testID="back-btn">
          <Ionicons name="chevron-back" size={26} color={tokens.text} />
        </Pressable>
        <View style={s.body}>
          <Text style={s.title}>{t('signIn')}</Text>
          <Text style={s.sub}>{t('tagline')}</Text>
          <Text style={s.loginTagline} testID="login-tagline">{t('loginTagline')}</Text>
          <TextInput
            testID="login-email"
            placeholder={t('email')}
            placeholderTextColor={tokens.textMute}
            autoCapitalize="none"
            keyboardType="email-address"
            style={s.input}
            value={email}
            onChangeText={setEmail}
          />
          <TextInput
            testID="login-password"
            placeholder={t('password')}
            placeholderTextColor={tokens.textMute}
            secureTextEntry
            style={s.input}
            value={password}
            onChangeText={setPassword}
          />
          <Pressable
            testID="login-forgot-password"
            onPress={() => router.push('/forgot-password')}
            style={s.forgotWrap}
            hitSlop={8}
          >
            <Text style={s.forgotText}>{t('forgotPassword')}</Text>
          </Pressable>
          {err ? <Text style={s.err}>{err}</Text> : null}
          <Pressable
            testID="login-submit"
            style={[s.btn, busy && { opacity: 0.5 }]}
            disabled={busy}
            onPress={submit}
          >
            <Text style={s.btnText}>{busy ? '…' : t('signIn')}</Text>
          </Pressable>
          <Pressable
            testID="goto-register"
            onPress={() => router.replace('/(auth)/register')}
          >
            <Text style={s.link}>
              {t('noAccount')} <Text style={{ color: tokens.brand }}>{t('signUp')}</Text>
            </Text>
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: tokens.bg },
  back: { padding: tokens.lg },
  body: { flex: 1, padding: tokens.xl, gap: tokens.md },
  title: { color: tokens.text, fontSize: 30, fontWeight: '900', letterSpacing: -0.5 },
  sub: { color: tokens.textMute, fontSize: 14, marginBottom: tokens.md },
  loginTagline: {
    color: tokens.brand,
    fontSize: 13,
    fontWeight: '600',
    marginTop: -8,
    marginBottom: tokens.md,
    letterSpacing: 0.3,
  },
  input: {
    backgroundColor: tokens.bg2,
    color: tokens.text,
    borderRadius: tokens.rLg,
    paddingHorizontal: 16,
    height: 56,
    fontSize: 16,
    borderWidth: 1,
    borderColor: tokens.border,
  },
  err: { color: tokens.danger, fontSize: 13 },
  forgotWrap: { alignSelf: 'flex-end', marginTop: -6, marginBottom: 2 },
  forgotText: { color: tokens.brand, fontSize: 13, fontWeight: '700' },
  btn: {
    backgroundColor: tokens.brand,
    height: 56,
    borderRadius: tokens.rLg,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: tokens.md,
  },
  btnText: { color: tokens.onBrand, fontSize: 16, fontWeight: '800' },
  link: { color: tokens.textDim, textAlign: 'center', marginTop: tokens.md },
});
