import { Ionicons } from '@expo/vector-icons';
import { Tabs, useRouter } from 'expo-router';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { tokens } from '@/src/theme';
import { t } from '@/src/i18n';

function ScanFab() {
  const router = useRouter();
  return (
    <View pointerEvents="box-none" style={s.fabWrap}>
      <Pressable
        testID="scan-fab"
        onPress={() => router.push('/scan')}
        style={s.fab}
      >
        <Ionicons name="scan-outline" size={26} color={tokens.onBrand} />
      </Pressable>
    </View>
  );
}

export default function TabsLayout() {
  return (
    <>
      <Tabs
        screenOptions={{
          headerShown: false,
          tabBarStyle: {
            backgroundColor: tokens.bg2,
            borderTopColor: tokens.border,
            height: 76,
            paddingBottom: 20,
            paddingTop: 8,
          },
          tabBarActiveTintColor: tokens.brand,
          tabBarInactiveTintColor: tokens.textMute,
          tabBarLabelStyle: { fontSize: 11, fontWeight: '700' },
        }}
      >
        <Tabs.Screen
          name="index"
          options={{
            title: t('home'),
            tabBarIcon: ({ color, size }) => (
              <Ionicons name="home" size={size} color={color} />
            ),
          }}
        />
        <Tabs.Screen
          name="diary"
          options={{
            title: t('diary'),
            tabBarIcon: ({ color, size }) => (
              <Ionicons name="restaurant" size={size} color={color} />
            ),
          }}
        />
        <Tabs.Screen
          name="coach"
          options={{
            title: t('coach'),
            tabBarIcon: ({ color, size }) => (
              <Ionicons name="sparkles" size={size} color={color} />
            ),
          }}
        />
        <Tabs.Screen
          name="profile"
          options={{
            title: t('profile'),
            tabBarIcon: ({ color, size }) => (
              <Ionicons name="person" size={size} color={color} />
            ),
          }}
        />
      </Tabs>
      <ScanFab />
    </>
  );
}

const s = StyleSheet.create({
  fabWrap: {
    position: 'absolute',
    left: 20,
    bottom: 124,
  },
  fab: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: tokens.brand,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: tokens.brand,
    shadowOpacity: 0.5,
    shadowRadius: 18,
    shadowOffset: { width: 0, height: 6 },
    elevation: 10,
  },
});
