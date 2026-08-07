import { Ionicons } from '@expo/vector-icons';
import { CameraView, useCameraPermissions } from 'expo-camera';
import * as ImageManipulator from 'expo-image-manipulator';
import * as ImagePicker from 'expo-image-picker';
import { useRouter } from 'expo-router';
import { useRef, useState } from 'react';
import {
  ActivityIndicator,
  Image,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { api } from '@/src/api';
import { t } from '@/src/i18n';
import { tokens } from '@/src/theme';

type Item = {
  name: string;
  portion_g: number;
  calories: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
  fiber_g: number;
  sugar_g: number;
};

type MealType = 'breakfast' | 'lunch' | 'dinner' | 'snack';

function today() {
  return new Date().toISOString().slice(0, 10);
}

export default function Scan() {
  const router = useRouter();
  const [perm, requestPerm] = useCameraPermissions();
  const camRef = useRef<CameraView>(null);
  const [photoB64, setPhotoB64] = useState<string | null>(null);
  const [photoUri, setPhotoUri] = useState<string | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeStep, setAnalyzeStep] = useState<'optimizing' | 'uploading' | 'analyzing' | ''>('');
  const [items, setItems] = useState<Item[] | null>(null);
  const [mealType, setMealType] = useState<MealType>('lunch');
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const runIdRef = useRef(0);

  // Resize/compress to keep the AI request small & fast. Cap the long edge at 1024px
  // and re-encode to JPEG at 0.55 quality. Base64 typically drops to ~80-150KB.
  const optimize = async (uri: string): Promise<{ base64: string; uri: string }> => {
    const result = await ImageManipulator.manipulateAsync(
      uri,
      [{ resize: { width: 1024 } }],
      { compress: 0.55, format: ImageManipulator.SaveFormat.JPEG, base64: true },
    );
    return { base64: result.base64 || '', uri: result.uri };
  };

  const capture = async () => {
    if (!camRef.current || analyzing) return;
    try {
      // Take a small preview-quality shot; we'll re-encode via manipulator anyway.
      const photo = await camRef.current.takePictureAsync({ quality: 0.5, base64: false, skipProcessing: true });
      if (!photo?.uri) return;
      setPhotoUri(photo.uri);
      await analyze(photo.uri);
    } catch (e: any) {
      setErr(e.message);
    }
  };

  const pickFromGallery = async () => {
    if (analyzing) return;
    const r = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      base64: false,
      quality: 1,
    });
    if (!r.canceled && r.assets[0]?.uri) {
      setPhotoUri(r.assets[0].uri);
      await analyze(r.assets[0].uri);
    }
  };

  const analyze = async (uri: string) => {
    const runId = ++runIdRef.current;
    setAnalyzing(true);
    setErr(null);
    setItems(null);
    setAnalyzeStep('optimizing');
    try {
      const opt = await optimize(uri);
      if (runId !== runIdRef.current) return;
      setPhotoB64(opt.base64);
      setPhotoUri(opt.uri);
      setAnalyzeStep('uploading');
      // brief tick so users see the progression update
      await new Promise((r) => setTimeout(r, 60));
      setAnalyzeStep('analyzing');
      const res = await api.scanMeal(opt.base64);
      if (runId !== runIdRef.current) return;
      setItems(res.items || []);
    } catch (e: any) {
      if (runId !== runIdRef.current) return;
      setErr(e.message || 'AI failed');
      setItems([]);
    } finally {
      if (runId === runIdRef.current) {
        setAnalyzing(false);
        setAnalyzeStep('');
      }
    }
  };

  const retake = () => {
    runIdRef.current++;
    setPhotoB64(null);
    setPhotoUri(null);
    setItems(null);
    setErr(null);
    setAnalyzing(false);
    setAnalyzeStep('');
  };

  const retry = () => {
    if (!photoUri || analyzing) return;
    analyze(photoUri);
  };

  const updateItem = (idx: number, field: keyof Item, value: number) => {
    if (!items) return;
    const next = [...items];
    (next[idx] as any)[field] = value;
    setItems(next);
  };

  const save = async () => {
    if (!items || items.length === 0) return;
    setSaving(true);
    try {
      await api.addMeal({
        meal_type: mealType,
        log_date: today(),
        items,
        photo_b64: null,
      });
      router.replace('/(tabs)/diary');
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setSaving(false);
    }
  };

  const totalCal = items?.reduce((a, i) => a + (i.calories || 0), 0) || 0;
  const totalP = items?.reduce((a, i) => a + (i.protein_g || 0), 0) || 0;
  const totalC = items?.reduce((a, i) => a + (i.carbs_g || 0), 0) || 0;
  const totalF = items?.reduce((a, i) => a + (i.fat_g || 0), 0) || 0;

  // Result / progress view (shown as soon as a photo is chosen)
  if (photoUri && (analyzing || items !== null)) {
    const stepText =
      analyzeStep === 'optimizing'
        ? 'Optimizing photo…'
        : analyzeStep === 'uploading'
        ? 'Uploading to AI…'
        : analyzeStep === 'analyzing'
        ? 'AI is identifying your meal…'
        : t('analyzing');
    return (
      <SafeAreaView style={s.wrap} edges={['top', 'bottom']}>
        <View style={s.headerRow}>
          <Pressable onPress={() => router.back()} style={s.iconBtn} testID="scan-close">
            <Ionicons name="close" size={22} color={tokens.text} />
          </Pressable>
          <Text style={s.headerTitle}>{t('confirmMeal')}</Text>
          <Pressable onPress={retake} style={s.iconBtn} testID="scan-retake">
            <Ionicons name="refresh" size={20} color={tokens.text} />
          </Pressable>
        </View>
        <ScrollView contentContainerStyle={{ padding: tokens.lg, paddingBottom: 140, gap: tokens.md }}>
          <Image source={{ uri: photoUri }} style={s.previewImg} />

          {analyzing && (
            <View style={s.analyzing} testID="scan-analyzing">
              <ActivityIndicator color={tokens.brand} size="large" />
              <Text style={s.analyzingText}>{stepText}</Text>
              <View style={s.stepDots}>
                <View
                  style={[
                    s.stepDot,
                    (analyzeStep === 'optimizing' ||
                      analyzeStep === 'uploading' ||
                      analyzeStep === 'analyzing') && s.stepDotActive,
                  ]}
                />
                <View
                  style={[
                    s.stepDot,
                    (analyzeStep === 'uploading' || analyzeStep === 'analyzing') && s.stepDotActive,
                  ]}
                />
                <View
                  style={[s.stepDot, analyzeStep === 'analyzing' && s.stepDotActive]}
                />
              </View>
              <Text style={s.analyzingHint}>This usually takes 5–15 seconds.</Text>
            </View>
          )}

          {!analyzing && err && (items === null || items.length === 0) && (
            <View style={s.errorCard} testID="scan-error">
              <Ionicons name="alert-circle" size={24} color={tokens.danger} />
              <Text style={s.errorText}>{err}</Text>
              <Pressable style={s.retryBtn} onPress={retry} testID="scan-retry">
                <Ionicons name="refresh" size={16} color={tokens.onBrand} />
                <Text style={s.retryText}>Try again</Text>
              </Pressable>
            </View>
          )}

          {!analyzing && !err && items !== null && items.length === 0 && (
            <View style={s.emptyState}>
              <Ionicons name="alert-circle-outline" size={28} color={tokens.textMute} />
              <Text style={s.emptyStateText}>{t('noItems')}</Text>
            </View>
          )}

          {items !== null && items.length > 0 && (
            <>
              <View style={s.totalsCard}>
                <Text style={s.totalsCal}>{Math.round(totalCal)} <Text style={s.totalsUnit}>kcal</Text></Text>
                <Text style={s.totalsMacro}>
                  P {Math.round(totalP)}g · C {Math.round(totalC)}g · F {Math.round(totalF)}g
                </Text>
              </View>

              <Text style={s.sectionLabel}>{t('which')}</Text>
              <View style={s.chipsRow}>
                {(['breakfast', 'lunch', 'dinner', 'snack'] as MealType[]).map((m) => (
                  <Pressable
                    key={m}
                    onPress={() => setMealType(m)}
                    style={[
                      s.chip,
                      mealType === m && { backgroundColor: tokens.brandTint, borderColor: tokens.brand },
                    ]}
                    testID={`meal-type-${m}`}
                  >
                    <Text style={[s.chipText, mealType === m && { color: tokens.brand, fontWeight: '800' }]}>
                      {t(m)}
                    </Text>
                  </Pressable>
                ))}
              </View>

              <Text style={s.sectionLabel}>Detected items</Text>
              {items.map((it, i) => (
                <View key={i} style={s.itemRow} testID={`scan-item-${i}`}>
                  <View style={{ flex: 1 }}>
                    <Text style={s.itemName}>{it.name}</Text>
                    <View style={s.itemFields}>
                      <FieldEdit
                        label="g"
                        value={it.portion_g}
                        onChange={(v) => updateItem(i, 'portion_g', v)}
                      />
                      <FieldEdit
                        label="kcal"
                        value={it.calories}
                        onChange={(v) => updateItem(i, 'calories', v)}
                      />
                      <FieldEdit
                        label="P"
                        value={it.protein_g}
                        onChange={(v) => updateItem(i, 'protein_g', v)}
                      />
                      <FieldEdit label="C" value={it.carbs_g} onChange={(v) => updateItem(i, 'carbs_g', v)} />
                      <FieldEdit label="F" value={it.fat_g} onChange={(v) => updateItem(i, 'fat_g', v)} />
                    </View>
                  </View>
                  <Pressable
                    onPress={() => setItems(items.filter((_, idx) => idx !== i))}
                    style={s.delBtn}
                    testID={`scan-remove-${i}`}
                  >
                    <Ionicons name="trash-outline" size={16} color={tokens.textMute} />
                  </Pressable>
                </View>
              ))}
              <Text style={s.disclaimer}>{t('disclaimer')}</Text>
            </>
          )}

          {err && <Text style={{ color: tokens.danger }}>{err}</Text>}
        </ScrollView>

        {items !== null && items.length > 0 && (
          <View style={s.footer}>
            <Pressable
              testID="scan-save"
              style={[s.saveBtn, saving && { opacity: 0.5 }]}
              disabled={saving}
              onPress={save}
            >
              <Ionicons name="checkmark" size={18} color={tokens.onBrand} />
              <Text style={s.saveBtnText}>{t('addToDiary')}</Text>
            </Pressable>
          </View>
        )}
      </SafeAreaView>
    );
  }

  // Camera view
  return (
    <View style={{ flex: 1, backgroundColor: '#000' }}>
      <SafeAreaView style={{ flex: 1 }} edges={['top', 'bottom']}>
        {!perm ? (
          <View style={s.center}>
            <ActivityIndicator color={tokens.brand} />
          </View>
        ) : !perm.granted ? (
          <View style={s.center}>
            <Ionicons name="camera-outline" size={40} color={tokens.textMute} />
            <Text style={{ color: tokens.text, fontSize: 15, textAlign: 'center', padding: 20 }}>
              We need your camera to scan meals.
            </Text>
            <Pressable style={s.primaryBtn} onPress={requestPerm} testID="grant-cam-btn">
              <Text style={s.primaryBtnText}>Grant camera access</Text>
            </Pressable>
            <Pressable style={s.altBtn} onPress={pickFromGallery} testID="alt-gallery-btn">
              <Text style={s.altBtnText}>{t('fromGallery')}</Text>
            </Pressable>
          </View>
        ) : (
          <>
            <CameraView ref={camRef} style={StyleSheet.absoluteFill} facing="back" />
            <View style={s.camOverlay}>
              <View style={s.camHeader}>
                <Pressable onPress={() => router.back()} style={s.iconBtn} testID="scan-back">
                  <Ionicons name="close" size={22} color="#fff" />
                </Pressable>
                <Text style={s.camTitle}>{t('scanTitle')}</Text>
                <View style={{ width: 40 }} />
              </View>
              <View style={s.frameWrap}>
                <View style={s.frame}>
                  <View style={[s.corner, s.tl]} />
                  <View style={[s.corner, s.tr]} />
                  <View style={[s.corner, s.bl]} />
                  <View style={[s.corner, s.br]} />
                </View>
                <Text style={s.hint}>{t('scanHint')}</Text>
              </View>
              <View style={s.camFooter}>
                <Pressable onPress={pickFromGallery} style={s.galleryBtn} testID="gallery-btn">
                  <Ionicons name="images" size={22} color="#fff" />
                </Pressable>
                <Pressable onPress={capture} style={s.capBtn} testID="capture-btn">
                  <View style={s.capInner} />
                </Pressable>
                <View style={{ width: 48 }} />
              </View>
            </View>
          </>
        )}
      </SafeAreaView>
    </View>
  );
}

function FieldEdit({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (n: number) => void;
}) {
  return (
    <View style={s.field}>
      <TextInput
        style={s.fieldInput}
        keyboardType="numeric"
        value={String(Math.round(value))}
        onChangeText={(txt) => {
          const n = parseFloat(txt);
          onChange(isNaN(n) ? 0 : n);
        }}
      />
      <Text style={s.fieldLabel}>{label}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: tokens.bg },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 16, padding: 24 },
  primaryBtn: {
    backgroundColor: tokens.brand,
    paddingHorizontal: 20,
    height: 48,
    borderRadius: 999,
    alignItems: 'center',
    justifyContent: 'center',
  },
  primaryBtnText: { color: tokens.onBrand, fontWeight: '800' },
  altBtn: { padding: 12 },
  altBtnText: { color: tokens.text, fontWeight: '600' },
  camOverlay: { ...StyleSheet.absoluteFillObject, justifyContent: 'space-between' },
  camHeader: {
    padding: tokens.lg,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  camTitle: { color: '#fff', fontSize: 16, fontWeight: '800' },
  iconBtn: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: 'rgba(255,255,255,0.15)', alignItems: 'center', justifyContent: 'center',
  },
  frameWrap: { alignItems: 'center', justifyContent: 'center' },
  frame: { width: 260, height: 260, borderRadius: 24, position: 'relative' },
  corner: { position: 'absolute', width: 34, height: 34, borderColor: tokens.brand, borderWidth: 3 },
  tl: { top: 0, left: 0, borderRightWidth: 0, borderBottomWidth: 0, borderTopLeftRadius: 24 },
  tr: { top: 0, right: 0, borderLeftWidth: 0, borderBottomWidth: 0, borderTopRightRadius: 24 },
  bl: { bottom: 0, left: 0, borderRightWidth: 0, borderTopWidth: 0, borderBottomLeftRadius: 24 },
  br: { bottom: 0, right: 0, borderLeftWidth: 0, borderTopWidth: 0, borderBottomRightRadius: 24 },
  hint: { color: '#fff', marginTop: 16, fontSize: 13 },
  camFooter: {
    padding: tokens.xl,
    paddingBottom: tokens.xxl,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  galleryBtn: {
    width: 48, height: 48, borderRadius: 24,
    backgroundColor: 'rgba(255,255,255,0.15)', alignItems: 'center', justifyContent: 'center',
  },
  capBtn: {
    width: 78, height: 78, borderRadius: 39, backgroundColor: 'rgba(255,255,255,0.2)',
    alignItems: 'center', justifyContent: 'center', borderWidth: 3, borderColor: '#fff',
  },
  capInner: { width: 58, height: 58, borderRadius: 29, backgroundColor: tokens.brand },
  headerRow: {
    padding: tokens.md,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderBottomWidth: 1,
    borderBottomColor: tokens.divider,
  },
  headerTitle: { color: tokens.text, fontSize: 16, fontWeight: '800' },
  previewImg: { width: '100%', height: 200, borderRadius: tokens.rLg, backgroundColor: tokens.bg2 },
  analyzing: {
    backgroundColor: tokens.bg2,
    padding: tokens.xl,
    borderRadius: tokens.rLg,
    alignItems: 'center',
    gap: 12,
    borderWidth: 1,
    borderColor: tokens.border,
  },
  analyzingText: { color: tokens.text, fontSize: 15, fontWeight: '700', textAlign: 'center' },
  analyzingHint: { color: tokens.textMute, fontSize: 12 },
  stepDots: { flexDirection: 'row', gap: 6, marginTop: 2 },
  stepDot: {
    width: 24, height: 4, borderRadius: 2, backgroundColor: tokens.bg3,
  },
  stepDotActive: { backgroundColor: tokens.brand },
  errorCard: {
    backgroundColor: tokens.bg2,
    padding: tokens.lg,
    borderRadius: tokens.rLg,
    alignItems: 'center',
    gap: 10,
    borderWidth: 1,
    borderColor: tokens.border,
  },
  errorText: { color: tokens.textDim, fontSize: 13, textAlign: 'center' },
  retryBtn: {
    flexDirection: 'row',
    gap: 6,
    alignItems: 'center',
    backgroundColor: tokens.brand,
    paddingHorizontal: 16,
    height: 40,
    borderRadius: 999,
    marginTop: 4,
  },
  retryText: { color: tokens.onBrand, fontWeight: '800', fontSize: 13 },
  emptyState: { alignItems: 'center', padding: tokens.lg, gap: 8 },
  emptyStateText: { color: tokens.textMute, fontSize: 14, textAlign: 'center' },
  totalsCard: {
    backgroundColor: tokens.brandTint,
    borderRadius: tokens.rLg,
    padding: tokens.lg,
    borderWidth: 1,
    borderColor: tokens.brand,
  },
  totalsCal: { color: tokens.brand, fontSize: 30, fontWeight: '900', letterSpacing: -0.5 },
  totalsUnit: { fontSize: 14, fontWeight: '700' },
  totalsMacro: { color: tokens.textDim, fontSize: 13, marginTop: 4 },
  sectionLabel: { color: tokens.textDim, fontSize: 12, fontWeight: '700', letterSpacing: 0.5, textTransform: 'uppercase' },
  chipsRow: { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
  chip: {
    paddingHorizontal: 14,
    height: 36,
    borderRadius: 999,
    backgroundColor: tokens.bg2,
    borderWidth: 1,
    borderColor: tokens.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  chipText: { color: tokens.textDim, fontSize: 13, fontWeight: '600' },
  itemRow: {
    flexDirection: 'row',
    gap: 8,
    padding: tokens.md,
    backgroundColor: tokens.bg2,
    borderRadius: tokens.rMd,
    borderWidth: 1,
    borderColor: tokens.border,
    alignItems: 'flex-start',
  },
  itemName: { color: tokens.text, fontSize: 15, fontWeight: '700', marginBottom: 8 },
  itemFields: { flexDirection: 'row', gap: 6, flexWrap: 'wrap' },
  field: { alignItems: 'center', minWidth: 52 },
  fieldInput: {
    backgroundColor: tokens.bg3,
    color: tokens.text,
    borderRadius: 8,
    paddingHorizontal: 8,
    paddingVertical: 6,
    minWidth: 52,
    textAlign: 'center',
    fontSize: 13,
    fontWeight: '700',
  },
  fieldLabel: { color: tokens.textMute, fontSize: 10, marginTop: 2 },
  delBtn: { padding: 6 },
  disclaimer: { color: tokens.textMute, fontSize: 11, marginTop: 6 },
  footer: {
    position: 'absolute',
    left: 0, right: 0, bottom: 0,
    padding: tokens.lg,
    backgroundColor: tokens.bg,
    borderTopWidth: 1,
    borderTopColor: tokens.divider,
  },
  saveBtn: {
    height: 56,
    borderRadius: tokens.rLg,
    backgroundColor: tokens.brand,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 8,
  },
  saveBtnText: { color: tokens.onBrand, fontSize: 16, fontWeight: '800' },
});
