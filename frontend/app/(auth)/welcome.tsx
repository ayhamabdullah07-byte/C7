import { useRouter } from 'expo-router';
import { LinearGradient } from 'expo-linear-gradient';
import { Image } from 'expo-image';
import { Ionicons } from '@expo/vector-icons';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { tokens } from '@/src/theme';
import { t } from '@/src/i18n';

export default function Welcome() {
  const router = useRouter();
  return (
    <View style={{ flex: 1, backgroundColor: tokens.bg }}>
      <Image
        source={{ uri: 'https://images.unsplash.com/photo-1621494268492-d01b98eba7e4?auto=format&fit=crop&w=1200&q=80' }}
        style={StyleSheet.absoluteFill}
        contentFit="cover"
        transition={200}
      />
      <LinearGradient
        colors={['rgba(10,10,12,0.2)', 'rgba(10,10,12,0.7)', tokens.bg]}
        style={StyleSheet.absoluteFill}
      />
      <SafeAreaView style={{ flex: 1 }} edges={['top', 'bottom']}>
        <View style={s.top}>
          <View style={s.logo} testID="welcome-logo">
            <Text style={s.logoC}>C1</Text>
          </View>
        </View>
        <View style={s.bottom}>
          <Text style={s.title}>{t('welcome')}</Text>
          <Text style={s.sub}>{t('tagline')}</Text>
          <Pressable
            testID="welcome-signup-btn"
            style={s.primary}
            onPress={() => router.push('/(auth)/register')}
          >
            <Text style={s.primaryText}>{t('signUp')}</Text>
          </Pressable>
          <Pressable
            testID="welcome-signin-btn"
            style={s.secondary}
            onPress={() => router.push('/(auth)/login')}
          >
            <Ionicons name="mail-outline" size={18} color={tokens.text} />
            <Text style={s.secondaryText}>{t('signIn')}</Text>
          </Pressable>
          <Text style={s.foot}>{t('medicalDisclaimer')}</Text>
        </View>
      </SafeAreaView>
    </View>
  );
}

const s = StyleSheet.create({
  top: { flex: 1, alignItems: 'center', paddingTop: 60 },
  logo: {
    width: 84,
    height: 84,
    borderRadius: 24,
    backgroundColor: tokens.brand,
    alignItems: 'center',
    justifyContent: 'center',
  },
  logoC: { color: tokens.onBrand, fontSize: 32, fontWeight: '900', letterSpacing: -1 },
  bottom: { padding: tokens.xl, paddingBottom: tokens.xxl, gap: tokens.md },
  title: { color: tokens.text, fontSize: 32, fontWeight: '900', letterSpacing: -0.5 },
  sub: { color: tokens.textDim, fontSize: 16, marginBottom: tokens.md },
  primary: {
    backgroundColor: tokens.brand,
    height: 56,
    borderRadius: tokens.rLg,
    alignItems: 'center',
    justifyContent: 'center',
  },
  primaryText: { color: tokens.onBrand, fontSize: 16, fontWeight: '800' },
  secondary: {
    backgroundColor: tokens.bg2,
    height: 56,
    borderRadius: tokens.rLg,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 8,
    borderWidth: 1,
    borderColor: tokens.border,
  },
  secondaryText: { color: tokens.text, fontSize: 16, fontWeight: '700' },
  foot: { color: tokens.textMute, fontSize: 11, textAlign: 'center', marginTop: tokens.sm, lineHeight: 16 },
});
