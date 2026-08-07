import { Ionicons } from '@expo/vector-icons';
import { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
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
import { useAuth } from '@/src/auth';
import { t } from '@/src/i18n';
import { tokens } from '@/src/theme';

type Msg = { id: string; role: 'user' | 'assistant'; content: string };

export default function Coach() {
  const { user } = useAuth();
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const listRef = useRef<FlatList>(null);
  const sessionId = user?.id ? `coach-${user.id}` : undefined;

  useEffect(() => {
    (async () => {
      if (!sessionId) return;
      try {
        const hist = await api.chatHistory(sessionId);
        setMessages(
          hist.map((m: any) => ({ id: m.id, role: m.role, content: m.content }))
        );
      } catch {}
    })();
  }, [sessionId]);

  const send = async (text?: string) => {
    const msg = (text ?? input).trim();
    if (!msg || sending) return;
    setInput('');
    const localId = `u-${Date.now()}`;
    setMessages((prev) => [...prev, { id: localId, role: 'user', content: msg }]);
    setSending(true);
    try {
      const r = await api.chat(msg, sessionId);
      setMessages((prev) => [
        ...prev,
        { id: `a-${Date.now()}`, role: 'assistant', content: r.reply },
      ]);
    } catch (e: any) {
      setMessages((prev) => [
        ...prev,
        { id: `err-${Date.now()}`, role: 'assistant', content: 'Sorry, something went wrong. Please try again.' },
      ]);
    } finally {
      setSending(false);
      setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 100);
    }
  };

  const suggestions = [t('suggest1'), t('suggest2'), t('suggest3')];

  return (
    <SafeAreaView style={s.wrap} edges={['top']}>
      <View style={s.header}>
        <View style={s.headerLeft}>
          <View style={s.avatar}>
            <Ionicons name="sparkles" size={16} color={tokens.onBrand} />
          </View>
          <View>
            <Text style={s.title}>C1 Coach</Text>
            <Text style={s.sub}>AI nutrition assistant</Text>
          </View>
        </View>
      </View>
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={80}
      >
        <FlatList
          ref={listRef}
          data={messages}
          keyExtractor={(m) => m.id}
          contentContainerStyle={s.body}
          onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: false })}
          ListEmptyComponent={
            <View style={s.empty} testID="coach-empty">
              <View style={s.greetAvatar}>
                <Ionicons name="sparkles" size={22} color={tokens.brand} />
              </View>
              <Text style={s.greet}>{t('coachGreet')}</Text>
              <View style={{ gap: 8 }}>
                {suggestions.map((sug, i) => (
                  <Pressable
                    key={i}
                    style={s.suggest}
                    onPress={() => send(sug)}
                    testID={`coach-suggest-${i}`}
                  >
                    <Text style={s.suggestText}>{sug}</Text>
                    <Ionicons name="arrow-forward" size={14} color={tokens.brand} />
                  </Pressable>
                ))}
              </View>
            </View>
          }
          renderItem={({ item }) => (
            <View
              style={[
                s.bubbleWrap,
                { justifyContent: item.role === 'user' ? 'flex-end' : 'flex-start' },
              ]}
            >
              <View
                style={[
                  s.bubble,
                  item.role === 'user' ? s.userBubble : s.aiBubble,
                ]}
                testID={`msg-${item.role}`}
              >
                <Text
                  style={[
                    s.bubbleText,
                    { color: item.role === 'user' ? tokens.onBrand : tokens.text },
                  ]}
                >
                  {item.content}
                </Text>
              </View>
            </View>
          )}
        />
        {sending && (
          <View style={s.typing}>
            <ActivityIndicator size="small" color={tokens.brand} />
            <Text style={s.typingText}>Coach is thinking…</Text>
          </View>
        )}
        <View style={s.inputBar}>
          <TextInput
            testID="coach-input"
            style={s.input}
            placeholder={t('askAnything')}
            placeholderTextColor={tokens.textMute}
            value={input}
            onChangeText={setInput}
            multiline
            onSubmitEditing={() => send()}
          />
          <Pressable
            testID="coach-send"
            style={[s.sendBtn, (!input.trim() || sending) && { opacity: 0.4 }]}
            disabled={!input.trim() || sending}
            onPress={() => send()}
          >
            <Ionicons name="send" size={18} color={tokens.onBrand} />
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: tokens.bg },
  header: {
    padding: tokens.lg,
    borderBottomWidth: 1,
    borderBottomColor: tokens.divider,
  },
  headerLeft: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  avatar: {
    width: 34,
    height: 34,
    borderRadius: 12,
    backgroundColor: tokens.brand,
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: { color: tokens.text, fontSize: 16, fontWeight: '800' },
  sub: { color: tokens.textMute, fontSize: 12 },
  body: { padding: tokens.lg, paddingBottom: 100, gap: tokens.sm },
  empty: { alignItems: 'center', gap: tokens.lg, marginTop: tokens.xl },
  greetAvatar: {
    width: 56, height: 56, borderRadius: 20, backgroundColor: tokens.brandTint,
    alignItems: 'center', justifyContent: 'center',
  },
  greet: { color: tokens.textDim, fontSize: 15, textAlign: 'center', lineHeight: 22, paddingHorizontal: 24 },
  suggest: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: tokens.bg2,
    borderRadius: 16,
    padding: 14,
    borderWidth: 1,
    borderColor: tokens.border,
  },
  suggestText: { color: tokens.text, fontSize: 14, fontWeight: '600', flex: 1 },
  bubbleWrap: { flexDirection: 'row', marginVertical: 4 },
  bubble: { maxWidth: '85%', paddingHorizontal: 14, paddingVertical: 10, borderRadius: 16 },
  userBubble: { backgroundColor: tokens.brand, borderBottomRightRadius: 4 },
  aiBubble: { backgroundColor: tokens.bg2, borderBottomLeftRadius: 4, borderWidth: 1, borderColor: tokens.border },
  bubbleText: { fontSize: 14, lineHeight: 20 },
  typing: { flexDirection: 'row', gap: 8, alignItems: 'center', paddingHorizontal: 20, paddingBottom: 6 },
  typingText: { color: tokens.textMute, fontSize: 12 },
  inputBar: {
    flexDirection: 'row',
    padding: tokens.md,
    paddingBottom: tokens.lg,
    gap: 8,
    borderTopWidth: 1,
    borderTopColor: tokens.divider,
    backgroundColor: tokens.bg,
    alignItems: 'flex-end',
  },
  input: {
    flex: 1,
    minHeight: 48,
    maxHeight: 140,
    backgroundColor: tokens.bg2,
    borderRadius: 24,
    paddingHorizontal: 16,
    paddingVertical: 12,
    color: tokens.text,
    fontSize: 15,
    borderWidth: 1,
    borderColor: tokens.border,
  },
  sendBtn: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: tokens.brand,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
