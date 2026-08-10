import AsyncStorage from '@react-native-async-storage/async-storage';

const BASE = process.env.EXPO_PUBLIC_BACKEND_URL as string;
const TOKEN_KEY = 'c1_token';

export async function setToken(t: string | null) {
  if (t) await AsyncStorage.setItem(TOKEN_KEY, t);
  else await AsyncStorage.removeItem(TOKEN_KEY);
}
export async function getToken(): Promise<string | null> {
  return AsyncStorage.getItem(TOKEN_KEY);
}

type ReqOpts = RequestInit & {
  timeoutMs?: number;
  retries?: number;
  retryOnStatus?: number[];
};

async function req(path: string, opts: ReqOpts = {}) {
  const {
    timeoutMs = 30000,
    retries = 0,
    retryOnStatus = [502, 503, 504],
    ...init
  } = opts;
  const token = await getToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init.headers as any),
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  let lastErr: any = null;
  for (let attempt = 0; attempt <= retries; attempt++) {
    const controller = new AbortController();
    const to = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const res = await fetch(`${BASE}/api${path}`, {
        ...init,
        headers,
        signal: controller.signal,
      });
      clearTimeout(to);
      const text = await res.text();
      let data: any = null;
      try {
        data = text ? JSON.parse(text) : null;
      } catch {
        data = text;
      }
      if (!res.ok) {
        if (retryOnStatus.includes(res.status) && attempt < retries) {
          await new Promise((r) => setTimeout(r, 800 * Math.pow(2, attempt)));
          continue;
        }
        const detail = data && data.detail;
        const msg =
          typeof detail === 'string'
            ? detail
            : detail && detail.message
            ? detail.message
            : `HTTP ${res.status}`;
        const e = new Error(msg) as Error & { status?: number; detail?: any };
        e.status = res.status;
        e.detail = detail;
        throw e;
      }
      return data;
    } catch (e: any) {
      clearTimeout(to);
      lastErr = e;
      const transient =
        e?.name === 'AbortError' ||
        /network|fetch/i.test(String(e?.message || ''));
      if (transient && attempt < retries) {
        await new Promise((r) => setTimeout(r, 800 * Math.pow(2, attempt)));
        continue;
      }
      if (e?.name === 'AbortError') {
        throw new Error('Request timed out. Please try again.');
      }
      throw e;
    }
  }
  throw lastErr || new Error('Request failed');
}

export const api = {
  register: (email: string, password: string, name: string) =>
    req('/auth/register', { method: 'POST', body: JSON.stringify({ email, password, name }) }),
  login: (email: string, password: string) =>
    req('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }),
  forgotPassword: (email: string) =>
    req('/auth/forgot-password', {
      method: 'POST',
      body: JSON.stringify({ email }),
      timeoutMs: 20000,
    }),
  resetPassword: (email: string, code: string, new_password: string) =>
    req('/auth/reset-password', {
      method: 'POST',
      body: JSON.stringify({ email, code, new_password }),
      timeoutMs: 20000,
    }),
  me: () => req('/auth/me'),
  updateProfile: (p: any) =>
    req('/auth/profile', { method: 'PATCH', body: JSON.stringify(p) }),
  entitlement: () => req('/entitlement'),
  verifyApple: (jws_representation: string, transaction_id: string, product_id: string) =>
    req('/iap/apple/verify', {
      method: 'POST',
      body: JSON.stringify({ jws_representation, transaction_id, product_id }),
    }),
  verifyGoogle: (
    purchase_token: string,
    subscription_id: string,
    base_plan_id: string,
    product_id: string,
  ) =>
    req('/iap/google/verify', {
      method: 'POST',
      body: JSON.stringify({ purchase_token, subscription_id, base_plan_id, product_id }),
    }),
  restore: (platform: 'apple' | 'google', entries: any[]) =>
    req('/iap/restore', { method: 'POST', body: JSON.stringify({ platform, entries }) }),
  scanQuota: () => req('/scan-quota'),
  deleteAccount: () => req('/auth/account', { method: 'DELETE' }),

  dashboard: (log_date?: string) =>
    req(`/dashboard${log_date ? `?log_date=${log_date}` : ''}`),
  listMeals: (log_date: string) => req(`/meals?log_date=${log_date}`),
  addMeal: (m: any) => req('/meals', { method: 'POST', body: JSON.stringify(m) }),
  deleteMeal: (id: string) => req(`/meals/${id}`, { method: 'DELETE' }),

  addWater: (log_date: string, amount_ml: number) =>
    req('/water', { method: 'POST', body: JSON.stringify({ log_date, amount_ml }) }),
  addWeight: (log_date: string, weight_kg: number) =>
    req('/weight', { method: 'POST', body: JSON.stringify({ log_date, weight_kg }) }),
  weightHistory: () => req('/weight'),

  scanMeal: (image_b64: string) =>
    req('/ai/scan-meal', {
      method: 'POST',
      body: JSON.stringify({ image_b64 }),
      timeoutMs: 90000,
      retries: 2,
    }),
  recommend: (focus: string, only: 'all' | 'meals' | 'snacks') =>
    req('/ai/recommend', {
      method: 'POST',
      body: JSON.stringify({ focus, only }),
      timeoutMs: 90000,
      retries: 1,
    }),
  refineRecommendation: (session_id: string, item: any, request: string) =>
    req('/ai/recommend/refine', {
      method: 'POST',
      body: JSON.stringify({ session_id, item, request }),
      timeoutMs: 90000,
      retries: 1,
    }),
  chat: (message: string, session_id?: string) =>
    req('/ai/chat-sync', { method: 'POST', body: JSON.stringify({ message, session_id }) }),
  chatHistory: (session_id: string) => req(`/ai/chat/history?session_id=${session_id}`),
};

export const BACKEND_URL = BASE;
