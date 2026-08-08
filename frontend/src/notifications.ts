import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';

const KEY = 'c1_notifications_enabled';
const SCHED_ID_KEY = 'c1_notification_ids';

// Configure default behavior for foreground notifications.
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: false,
    shouldSetBadge: false,
  }),
});

export async function isEnabled(): Promise<boolean> {
  const v = await AsyncStorage.getItem(KEY);
  return v === '1';
}

export async function setEnabledFlag(v: boolean) {
  await AsyncStorage.setItem(KEY, v ? '1' : '0');
}

export async function requestPermission(): Promise<boolean> {
  const settings = await Notifications.getPermissionsAsync();
  if (settings.granted) return true;
  if (!settings.canAskAgain) return false;
  const req = await Notifications.requestPermissionsAsync({
    ios: { allowAlert: true, allowBadge: false, allowSound: false },
  });
  return !!req.granted;
}

export async function cancelAll() {
  const raw = await AsyncStorage.getItem(SCHED_ID_KEY);
  if (raw) {
    try {
      const ids: string[] = JSON.parse(raw);
      await Promise.all(ids.map((id) => Notifications.cancelScheduledNotificationAsync(id).catch(() => {})));
    } catch {}
  }
  await AsyncStorage.removeItem(SCHED_ID_KEY);
}

/**
 * Schedule 2 daily reminders:
 * - 11:00 – midday nudge
 * - 19:00 – evening remaining-calorie reminder
 */
export async function scheduleDailyReminders(userName?: string) {
  await cancelAll();
  if (Platform.OS === 'android') {
    // Ensure a channel exists for Android reliability
    try {
      await Notifications.setNotificationChannelAsync('c1-daily', {
        name: 'C1 daily reminders',
        importance: Notifications.AndroidImportance.DEFAULT,
      });
    } catch {}
  }
  const midday = await Notifications.scheduleNotificationAsync({
    content: {
      title: 'C1 — Time to log lunch 🍽️',
      body: `Hey${userName ? ' ' + userName : ''}, keep your day on track — log what you had for lunch.`,
    },
    trigger: {
      type: Notifications.SchedulableTriggerInputTypes.DAILY,
      hour: 11,
      minute: 0,
    } as any,
  });
  const evening = await Notifications.scheduleNotificationAsync({
    content: {
      title: 'C1 — How\u2019s your day looking? 🎯',
      body: 'Check remaining calories & macros — a healthy dinner is a great finish.',
    },
    trigger: {
      type: Notifications.SchedulableTriggerInputTypes.DAILY,
      hour: 19,
      minute: 0,
    } as any,
  });
  await AsyncStorage.setItem(SCHED_ID_KEY, JSON.stringify([midday, evening]));
}

export async function enableForPlus(userName?: string): Promise<boolean> {
  const granted = await requestPermission();
  if (!granted) {
    await setEnabledFlag(false);
    return false;
  }
  await scheduleDailyReminders(userName);
  await setEnabledFlag(true);
  return true;
}

export async function disable() {
  await cancelAll();
  await setEnabledFlag(false);
}
