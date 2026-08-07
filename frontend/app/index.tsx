import { useEffect } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { useAuth } from '@/src/auth';
import { tokens } from '@/src/theme';

export default function Index() {
  const router = useRouter();
  const { user, bootDone } = useAuth();

  useEffect(() => {
    if (!bootDone) return;
    if (!user) router.replace('/(auth)/welcome');
    else if (!user.onboarded) router.replace('/(onboarding)/step-1');
    else router.replace('/(tabs)');
  }, [user, bootDone, router]);

  return (
    <View style={styles.wrap} testID="splash-screen">
      <View style={styles.logoWrap} testID="c1-logo">
        <View style={styles.logoCircle}>
          <Text style={styles.logoC}>C</Text>
          <View style={styles.logoOne}>
            <Text style={styles.logoOneText}>1</Text>
          </View>
        </View>
        <Text style={styles.brand}>C1</Text>
        <Text style={styles.tag}>Your AI nutrition coach</Text>
      </View>
      <ActivityIndicator color={tokens.brand} />
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flex: 1,
    backgroundColor: tokens.bg,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 24,
  },
  logoWrap: { alignItems: 'center', gap: 12 },
  logoCircle: {
    width: 96,
    height: 96,
    borderRadius: 28,
    backgroundColor: tokens.brand,
    alignItems: 'center',
    justifyContent: 'center',
    position: 'relative',
    shadowColor: tokens.brand,
    shadowOpacity: 0.35,
    shadowRadius: 20,
    shadowOffset: { width: 0, height: 6 },
    elevation: 8,
  },
  logoC: { color: tokens.onBrand, fontSize: 54, fontWeight: '900', letterSpacing: -3 },
  logoOne: {
    position: 'absolute',
    right: 8,
    bottom: 8,
    backgroundColor: tokens.bg,
    borderRadius: 12,
    width: 28,
    height: 28,
    alignItems: 'center',
    justifyContent: 'center',
  },
  logoOneText: { color: tokens.brand, fontWeight: '900', fontSize: 18 },
  brand: { color: tokens.text, fontSize: 36, fontWeight: '900', letterSpacing: -1 },
  tag: { color: tokens.textMute, fontSize: 13, letterSpacing: 0.5 },
});
