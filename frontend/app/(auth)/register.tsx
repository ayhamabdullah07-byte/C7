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

export default function Register() {
  const router = useRouter();
  const { signUp } = useAuth();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setErr(null);
    if (name.trim().length < 2) return setErr('Please enter your name');
    if (password.length < 6) return setErr('Password must be 6+ chars');
    setBusy(true);
    try {
      await signUp(email.trim().toLowerCase(), password, name.trim());
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
          <Text style={s.title}>{t('signUp')}</Text>
          <Text style={s.sub}>{t('tagline')}</Text>
          <TextInput
            testID="register-name"
            placeholder={t('name')}
            placeholderTextColor={tokens.textMute}
            style={s.input}
            value={name}
            onChangeText={setName}
          />
          <TextInput
            testID="register-email"
            placeholder={t('email')}
            placeholderTextColor={tokens.textMute}
            autoCapitalize="none"
            keyboardType="email-address"
            style={s.input}
            value={email}
            onChangeText={setEmail}
          />
          <TextInput
            testID="register-password"
            placeholder={t('password')}
            placeholderTextColor={tokens.textMute}
            secureTextEntry
            style={s.input}
            value={password}
            onChangeText={setPassword}
          />
          {err ? <Text style={s.err}>{err}</Text> : null}
          <Pressable
            testID="register-submit"
            style={[s.btn, busy && { opacity: 0.5 }]}
            disabled={busy}
            onPress={submit}
          >
            <Text style={s.btnText}>{busy ? '…' : t('signUp')}</Text>
          </Pressable>
          <Pressable
            testID="goto-login"
            onPress={() => router.replace('/(auth)/login')}
          >
            <Text style={s.link}>
              {t('haveAccount')} <Text style={{ color: tokens.brand }}>{t('signIn')}</Text>
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
