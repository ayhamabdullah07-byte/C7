import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
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
import { api } from '@/src/api';
import { t } from '@/src/i18n';
import { tokens } from '@/src/theme';

type Stage = 'request' | 'verify' | 'done';

export default function ForgotPassword() {
  const router = useRouter();
  const [stage, setStage] = useState<Stage>('request');
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const requestCode = async () => {
    setErr(null);
    setMsg(null);
    const clean = email.trim().toLowerCase();
    if (!/^\S+@\S+\.\S+$/.test(clean)) {
      setErr('Please enter a valid email address.');
      return;
    }
    setBusy(true);
    try {
      await api.forgotPassword(clean);
      setEmail(clean);
      setMsg(t('codeSent'));
      setStage('verify');
    } catch (e: any) {
      setErr(e.message || t('errors'));
    } finally {
      setBusy(false);
    }
  };

  const submitReset = async () => {
    setErr(null);
    setMsg(null);
    if (!/^\d{6}$/.test(code.trim())) {
      setErr('Enter the 6-digit code sent to your email.');
      return;
    }
    if (newPassword.length < 6) {
      setErr('Password must be at least 6 characters.');
      return;
    }
    setBusy(true);
    try {
      await api.resetPassword(email, code.trim(), newPassword);
      setStage('done');
    } catch (e: any) {
      setErr(e.message || t('errors'));
    } finally {
      setBusy(false);
    }
  };

  const resend = async () => {
    setErr(null);
    setBusy(true);
    try {
      await api.forgotPassword(email);
      setMsg(t('codeSent'));
    } catch (e: any) {
      setErr(e.message);
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
        <Pressable
          onPress={() => router.back()}
          style={s.back}
          testID="forgot-back"
          hitSlop={8}
        >
          <Ionicons name="chevron-back" size={26} color={tokens.text} />
        </Pressable>

        <View style={s.body}>
          <View style={s.iconBadge}>
            <Ionicons
              name={stage === 'done' ? 'checkmark' : 'lock-closed'}
              size={26}
              color={tokens.brand}
            />
          </View>
          <Text style={s.title} testID="forgot-title">
            {stage === 'done' ? 'All set' : t('resetTitle')}
          </Text>
          <Text style={s.sub}>
            {stage === 'request'
              ? t('resetSub')
              : stage === 'verify'
              ? `We sent a 6-digit code to ${email}. Enter it below.`
              : t('passwordChanged')}
          </Text>

          {stage === 'request' && (
            <>
              <TextInput
                testID="forgot-email"
                placeholder={t('email')}
                placeholderTextColor={tokens.textMute}
                autoCapitalize="none"
                keyboardType="email-address"
                style={s.input}
                value={email}
                onChangeText={setEmail}
              />
              {err ? <Text style={s.err}>{err}</Text> : null}
              <Pressable
                testID="forgot-send-code"
                style={[s.btn, busy && { opacity: 0.5 }]}
                disabled={busy}
                onPress={requestCode}
              >
                <Text style={s.btnText}>{busy ? '…' : t('sendCode')}</Text>
              </Pressable>
              <Pressable
                testID="forgot-back-to-login"
                onPress={() => router.replace('/(auth)/login')}
              >
                <Text style={s.link}>
                  Remembered it? <Text style={{ color: tokens.brand }}>{t('signIn')}</Text>
                </Text>
              </Pressable>
            </>
          )}

          {stage === 'verify' && (
            <>
              {msg ? (
                <View style={s.infoBox} testID="forgot-code-sent">
                  <Ionicons name="mail" size={16} color={tokens.success} />
                  <Text style={s.infoText}>{msg}</Text>
                </View>
              ) : null}
              <TextInput
                testID="forgot-code"
                placeholder={t('enterCode')}
                placeholderTextColor={tokens.textMute}
                keyboardType="number-pad"
                maxLength={6}
                style={[s.input, { letterSpacing: 6, textAlign: 'center', fontSize: 22, fontWeight: '800' }]}
                value={code}
                onChangeText={(v) => setCode(v.replace(/\D/g, ''))}
              />
              <TextInput
                testID="forgot-new-password"
                placeholder={t('newPassword')}
                placeholderTextColor={tokens.textMute}
                secureTextEntry
                style={s.input}
                value={newPassword}
                onChangeText={setNewPassword}
              />
              {err ? <Text style={s.err}>{err}</Text> : null}
              <Pressable
                testID="forgot-submit-reset"
                style={[s.btn, busy && { opacity: 0.5 }]}
                disabled={busy}
                onPress={submitReset}
              >
                <Text style={s.btnText}>{busy ? '…' : t('resetSubmit')}</Text>
              </Pressable>
              <Pressable testID="forgot-resend" onPress={resend} disabled={busy}>
                <Text style={s.link}>
                  <Text style={{ color: tokens.brand }}>{t('didntGetCode')}</Text>
                </Text>
              </Pressable>
            </>
          )}

          {stage === 'done' && (
            <Pressable
              testID="forgot-goto-signin"
              style={s.btn}
              onPress={() => router.replace('/(auth)/login')}
            >
              <Text style={s.btnText}>{t('signIn')}</Text>
            </Pressable>
          )}
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: tokens.bg },
  back: { padding: tokens.lg },
  body: { flex: 1, padding: tokens.xl, gap: tokens.md },
  iconBadge: {
    width: 60,
    height: 60,
    borderRadius: 18,
    backgroundColor: tokens.brandTint,
    borderWidth: 1,
    borderColor: tokens.brand,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 6,
  },
  title: { color: tokens.text, fontSize: 28, fontWeight: '900', letterSpacing: -0.5 },
  sub: { color: tokens.textMute, fontSize: 14, lineHeight: 20, marginBottom: tokens.md },
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
  infoBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    padding: 12,
    borderRadius: 12,
    backgroundColor: 'rgba(52,211,153,0.10)',
    borderWidth: 1,
    borderColor: 'rgba(52,211,153,0.4)',
  },
  infoText: { color: tokens.textDim, fontSize: 12, flex: 1 },
});
