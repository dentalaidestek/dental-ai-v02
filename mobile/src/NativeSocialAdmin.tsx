import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  AppState,
  Image,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useFocusEffect } from "@react-navigation/native";
import { User } from "./api";
import * as api from "./socialApi";

type Props = { token: string; user: User };
type Mode = "queue" | "reports";
type Kind = api.SocialAdminKind;
type Status = api.SocialAdminStatus;
type RecordItem = Record<string, unknown> & { id: number; version?: number; status?: string };

const C = {
  navy: "#071B35",
  text: "#102033",
  muted: "#52647B",
  line: "#E5EAF0",
  bg: "#F5F7FA",
  red: "#B42318",
  green: "#16794A",
};

const kinds: { value: Kind; label: string }[] = [
  { value: "POST", label: "Gönderiler" },
  { value: "COMMENT", label: "Yorumlar" },
  { value: "PUBLICATION", label: "Akademik yayınlar" },
];
const statuses: { value: Status; label: string }[] = [
  { value: "PENDING", label: "İncelemede" },
  { value: "PUBLISHED", label: "Yayınlandı" },
  { value: "REJECTED", label: "Reddedildi" },
];

function asText(value: unknown, max = 1200): string {
  return typeof value === "string" ? value.slice(0, max) : "";
}
function actionLabel(status: Status): string {
  return status === "PUBLISHED" ? "Yayınla" : status === "REJECTED" ? "Reddet" : "Düzenleme iste";
}

export default function NativeSocialAdmin({ token, user }: Props) {
  const isAdmin = String(user.role || "").toUpperCase() === "ADMIN";
  const [challengeSent, setChallengeSent] = useState(false);
  const [code, setCode] = useState("");
  const [stepUpToken, setStepUpToken] = useState<string | null>(null);
  const [expiresAt, setExpiresAt] = useState(0);
  const [mode, setMode] = useState<Mode>("queue");
  const [kind, setKind] = useState<Kind>("POST");
  const [status, setStatus] = useState<Status>("PENDING");
  const [items, setItems] = useState<RecordItem[]>([]);
  const [cursor, setCursor] = useState<string | number | null>(null);
  const [detail, setDetail] = useState<api.SocialAdminDetail | null>(null);
  const [detailKind, setDetailKind] = useState<Kind>("POST");
  const [decisionReason, setDecisionReason] = useState("");
  const [aging, setAging] = useState<Record<string, number> | undefined>();
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const grantRef = useRef<string | null>(null);
  const generation = useRef(0);
  const loadingRef = useRef(false);
  const cursorRef = useRef<string | number | null>(null);
  const mounted = useRef(true);

  const clearGrant = useCallback(async (updateUi: boolean) => {
    const current = grantRef.current;
    grantRef.current = null;
    generation.current++;
    loadingRef.current = false;
    if (updateUi && mounted.current) {
      setStepUpToken(null);
      setExpiresAt(0);
      setItems([]);
      setCursor(null);
      cursorRef.current = null;
      setDetail(null);
      setAging(undefined);
      setLoading(false);
    }
    if (current) {
      try {
        await api.revokeSocialAdminStepUp(token, current);
      } catch {
        // Server expiry and bearer-session binding remain the final authority.
      }
    }
  }, [token]);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      generation.current++;
      void clearGrant(false);
    };
  }, [clearGrant]);

  useFocusEffect(useCallback(() => {
    if (!grantRef.current) {
      setStepUpToken(null);
      setExpiresAt(0);
      setItems([]);
      setCursor(null);
      setDetail(null);
    }
    return () => {
      generation.current++;
      void clearGrant(false);
    };
  }, [clearGrant]));

  useEffect(() => {
    const subscription = AppState.addEventListener("change", (state) => {
      if (state !== "active" && grantRef.current) {
        generation.current++;
        void clearGrant(true);
        setNotice("Güvenlik için yönetici oturumu kapatıldı. Devam etmek için yeniden doğrulayın.");
      }
    });
    return () => subscription.remove();
  }, [clearGrant]);

  useEffect(() => {
    if (!expiresAt) return;
    const timer = setTimeout(() => {
      void clearGrant(true);
      setNotice("Beş dakikalık yönetici doğrulaması sona erdi. Yeniden doğrulayın.");
    }, Math.max(0, expiresAt - Date.now()));
    return () => clearTimeout(timer);
  }, [expiresAt, clearGrant]);

  const begin = async () => {
    if (!isAdmin || busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await api.beginSocialAdminStepUp(token);
      setChallengeSent(true);
      setCode("");
      setNotice("Altı haneli kod sabit yönetici e-posta adresine gönderildi. Kod 10 dakika geçerlidir.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Doğrulama kodu gönderilemedi.");
    } finally {
      setBusy(false);
    }
  };

  const verify = async () => {
    if (!isAdmin || busy || !/^\d{6}$/.test(code)) return;
    setBusy(true);
    setError("");
    try {
      const grant = await api.verifySocialAdminStepUp(token, code);
      grantRef.current = grant.token;
      setStepUpToken(grant.token);
      setExpiresAt(Date.now() + grant.expires_in * 1000);
      setChallengeSent(false);
      setCode("");
      setNotice("Yönetici moderasyon erişimi açıldı. Yetki yalnızca bu ekranda ve beş dakika geçerlidir.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Kod doğrulanamadı.");
    } finally {
      setBusy(false);
    }
  };

  const load = useCallback(async (reset = true) => {
    const grant = grantRef.current;
    if (!grant || (!reset && loadingRef.current)) return;
    const request = ++generation.current;
    const before = reset ? null : cursorRef.current;
    loadingRef.current = true;
    setLoading(true);
    setError("");
    if (reset) {
      setItems([]);
      setCursor(null);
      cursorRef.current = null;
      setAging(undefined);
    }
    try {
      if (mode === "reports") {
        const page = await api.getSocialAdminReports(
          token,
          grant,
          typeof before === "number" ? before : null,
        );
        if (request !== generation.current || grantRef.current !== grant) return;
        setItems((current) => reset
          ? page.items
          : [...current, ...page.items.filter((row) => !current.some((old) => old.id === row.id))]);
        cursorRef.current = page.next_cursor;
        cursorRef.current = page.next_cursor;
        setCursor(page.next_cursor);
      } else {
        const page = await api.getSocialAdminQueue(token, grant, kind, status, before);
        if (request !== generation.current || grantRef.current !== grant) return;
        setItems((current) => reset
          ? page.items
          : [...current, ...page.items.filter((row) => !current.some((old) => old.id === row.id))]);
        setCursor(page.next_cursor);
        setAging(page.aging);
      }
    } catch (e) {
      if (request === generation.current) {
        setError(e instanceof Error ? e.message : "Liste yüklenemedi.");
      }
    } finally {
      if (request === generation.current) {
        loadingRef.current = false;
        setLoading(false);
      }
    }
  }, [token, mode, kind, status]);

  useEffect(() => {
    if (stepUpToken && grantRef.current === stepUpToken) void load(true);
  }, [stepUpToken, mode, kind, status, load]);

  const openDetail = async (targetKind: Kind, id: number) => {
    const grant = grantRef.current;
    if (!grant || busy) return;
    setBusy(true);
    setError("");
    try {
      const value = await api.getSocialAdminDetail(token, grant, targetKind, id);
      if (grantRef.current !== grant) return;
      setDetail(value);
      setDetailKind(targetKind);
      setDecisionReason("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "İçerik ayrıntısı yüklenemedi.");
    } finally {
      setBusy(false);
    }
  };

  const decide = async (next: Status) => {
    const grant = grantRef.current;
    const item = detail?.item;
    const id = item?.id;
    const version = item?.version;
    if (!grant || !Number.isSafeInteger(id) || !Number.isSafeInteger(version) ||
        decisionReason.trim().length < 3 || decisionReason.trim().length > 300 || busy) {
      setError("Karar için en az üç karakterlik, kişisel veri içermeyen bir gerekçe yazın.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await api.decideSocialAdminModeration(
        token, grant, detailKind, id as number, next, version as number, decisionReason,
      );
      if (grantRef.current !== grant) return;
      setDetail(null);
      setDecisionReason("");
      setNotice(next === "PUBLISHED" ? "İçerik yayınlandı." : next === "REJECTED" ? "İçerik reddedildi." : "Düzenleme isteği iletildi.");
      await load(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Karar kaydedilemedi. İçerik sürümünü yenileyin.");
      if (grantRef.current === grant) await load(true);
    } finally {
      setBusy(false);
    }
  };

  const openReport = (item: RecordItem) => {
    const targetKind = item.target_type === "COMMENT" ? "COMMENT" : "POST";
    const targetId = item.target_id;
    if (Number.isSafeInteger(targetId) && (targetId as number) > 0) {
      void openDetail(targetKind, targetId as number);
    }
  };

  const renderMedia = (item: Record<string, unknown>) => {
    const media = Array.isArray(item.media) ? item.media.slice(0, 4) : [];
    if (!media.length) return null;
    return (
      <View style={styles.mediaGrid}>
        {media.map((entry, index) => {
          if (!entry || typeof entry !== "object") return null;
          const row = entry as Record<string, unknown>;
          if (typeof row.url !== "string") return null;
          return (
            <Image
              key={String(row.id || index)}
              source={api.socialImageSource(row.url, token)}
              resizeMode="contain"
              style={styles.media}
              accessibilityLabel="İncelenen gönderi görseli"
            />
          );
        })}
      </View>
    );
  };

  const renderQueueItem = (item: RecordItem) => (
    <View key={item.id} style={styles.card}>
      <Text style={styles.cardTitle}>
        {kind === "POST" ? "Gönderi" : kind === "COMMENT" ? "Yorum" : "Akademik yayın"} #{item.id}
      </Text>
      <Text style={styles.muted}>{asText(item.author_name, 120) || asText(item.authors, 160)}</Text>
      <Text style={styles.body}>{asText(item.text || item.title || item.description || item.authors)}</Text>
      <Pressable accessibilityRole="button" style={styles.secondary} onPress={() => void openDetail(kind, item.id)}>
        <Text style={styles.secondaryText}>İçeriği ve karar geçmişini incele</Text>
      </Pressable>
    </View>
  );

  if (!isAdmin) {
    return (
      <SafeAreaView style={styles.page}>
        <View style={styles.pad}>
          <Text style={styles.title}>Yönetici moderasyonu</Text>
          <Text style={styles.error}>Bu alan yalnızca yönetici hesabına açıktır.</Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.page}>
      <ScrollView contentContainerStyle={styles.pad} keyboardShouldPersistTaps="handled">
        <Text style={styles.title}>Dental Akış moderasyonu</Text>
        <Text style={styles.muted}>
          İnsan incelemesi ve şikâyetler. Otomatik işaretler tek başına karar değildir.
          Karar gerekçesine hasta kimliği veya sağlık verisi yazmayın.
        </Text>

        {!stepUpToken ? (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>Yönetici doğrulaması</Text>
            <Text style={styles.muted}>Sabit yönetici e-posta adresine tek kullanımlık kod gönderilir. Doğrulama beş dakika geçerlidir.</Text>
            {!challengeSent ? (
              <Pressable accessibilityRole="button" disabled={busy} style={styles.primary} onPress={() => void begin()}>
                <Text style={styles.primaryText}>{busy ? "Gönderiliyor…" : "Doğrulama kodu gönder"}</Text>
              </Pressable>
            ) : (
              <>
                <TextInput
                  accessibilityLabel="Altı haneli yönetici doğrulama kodu"
                  value={code}
                  onChangeText={(value) => setCode(value.replace(/[^0-9]/g, "").slice(0, 6))}
                  keyboardType="number-pad"
                  textContentType="oneTimeCode"
                  maxLength={6}
                  placeholder="000000"
                  style={styles.codeInput}
                />
                <Pressable accessibilityRole="button" disabled={busy || code.length !== 6} style={[styles.primary, (busy || code.length !== 6) && styles.disabled]} onPress={() => void verify()}>
                  <Text style={styles.primaryText}>{busy ? "Doğrulanıyor…" : "Kodu doğrula"}</Text>
                </Pressable>
                <Pressable accessibilityRole="button" disabled={busy} style={styles.secondary} onPress={() => { setChallengeSent(false); setCode(""); }}>
                  <Text style={styles.secondaryText}>Vazgeç</Text>
                </Pressable>
              </>
            )}
          </View>
        ) : (
          <>
            <View style={styles.grantRow}>
              <View style={{ flex: 1 }}>
                <Text style={styles.grantTitle}>Yönetici erişimi açık</Text>
                <Text style={styles.muted}>Bu ekrandan ayrılınca, uygulama arka plana geçince veya süre dolunca yetki iptal edilir.</Text>
              </View>
              <Pressable accessibilityRole="button" onPress={() => void clearGrant(true)} style={styles.secondary}>
                <Text style={styles.secondaryText}>Kapat</Text>
              </Pressable>
            </View>

            <View style={styles.row}>
              <Pressable accessibilityRole="button" onPress={() => { setMode("queue"); setDetail(null); }} style={[styles.chip, mode === "queue" && styles.chipSelected]}>
                <Text style={[styles.chipText, mode === "queue" && styles.chipTextSelected]}>İnceleme kuyruğu</Text>
              </Pressable>
              <Pressable accessibilityRole="button" onPress={() => { setMode("reports"); setDetail(null); }} style={[styles.chip, mode === "reports" && styles.chipSelected]}>
                <Text style={[styles.chipText, mode === "reports" && styles.chipTextSelected]}>Şikâyetler</Text>
              </Pressable>
            </View>

            {mode === "queue" && (
              <>
                <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.filterRow}>
                  {kinds.map((entry) => (
                    <Pressable key={entry.value} accessibilityRole="button" onPress={() => { setKind(entry.value); setDetail(null); }} style={[styles.chip, kind === entry.value && styles.chipSelected]}>
                      <Text style={[styles.chipText, kind === entry.value && styles.chipTextSelected]}>{entry.label}</Text>
                    </Pressable>
                  ))}
                </ScrollView>
                <View style={styles.row}>
                  {statuses.map((entry) => (
                    <Pressable key={entry.value} accessibilityRole="button" onPress={() => { setStatus(entry.value); setDetail(null); }} style={[styles.chip, status === entry.value && styles.chipSelected]}>
                      <Text style={[styles.chipText, status === entry.value && styles.chipTextSelected]}>{entry.label}</Text>
                    </Pressable>
                  ))}
                </View>
                {aging && <Text style={styles.muted}>Bekleyen: {aging.waiting_human ?? 0} · Düzenleme: {aging.waiting_owner ?? 0} · Hata: {aging.failed ?? 0} · 1 saat+: {aging.over_1h ?? 0} · 24 saat+: {aging.over_24h ?? 0}</Text>}
              </>
            )}

            {detail ? (
              <View style={styles.card}>
                <Text style={styles.cardTitle}>İçerik #{String(detail.item.id)}</Text>
                <Text style={styles.muted}>{asText(detail.item.author_name, 120) || asText(detail.item.authors, 160)}</Text>
                <Text style={styles.body}>{asText(detail.item.text || detail.item.title || detail.item.description || detail.item.authors)}</Text>
                {renderMedia(detail.item)}
                <Text style={styles.sectionTitle}>Karar geçmişi</Text>
                {detail.history.map((row, index) => (
                  <Text key={String(row.id || index)} style={styles.history}>
                    {asText(row.created_at, 40)} · {asText(row.status, 30)} · {asText(row.reason, 300)}
                  </Text>
                ))}
                {detail.moderation_history.map((row, index) => (
                  <Text key={"m" + String(row.id || index)} style={styles.history}>
                    {asText(row.created_at, 40)} · {asText(row.source, 30)} · {asText(row.state, 40)} · {asText(row.reason, 300)}
                  </Text>
                ))}
                <Text style={styles.sectionTitle}>Karar gerekçesi</Text>
                <TextInput
                  accessibilityLabel="Kişisel veri içermeyen karar gerekçesi"
                  value={decisionReason}
                  onChangeText={(value) => setDecisionReason(value.slice(0, 300))}
                  multiline
                  maxLength={300}
                  placeholder="En az 3 karakter; hasta bilgisi yazmayın"
                  style={styles.input}
                />
                <View style={styles.row}>
                  {statuses.map((entry) => (
                    <Pressable key={entry.value} accessibilityRole="button" disabled={busy || decisionReason.trim().length < 3} style={[styles.decision, (busy || decisionReason.trim().length < 3) && styles.disabled]} onPress={() => void decide(entry.value)}>
                      <Text style={styles.decisionText}>{actionLabel(entry.value)}</Text>
                    </Pressable>
                  ))}
                </View>
                <Pressable accessibilityRole="button" style={styles.secondary} onPress={() => setDetail(null)}>
                  <Text style={styles.secondaryText}>Listeye dön</Text>
                </Pressable>
              </View>
            ) : (
              <>
                {items.map((item) => mode === "reports" ? (
                  <View key={item.id} style={styles.card}>
                    <Text style={styles.cardTitle}>Şikâyet #{item.id} · {asText(item.reason, 80)}</Text>
                    <Text style={styles.muted}>Üye #{String(item.reporter_id ?? "—").slice(0, 30)} · {asText(item.created_at, 40)}</Text>
                    <Pressable accessibilityRole="button" style={styles.secondary} onPress={() => openReport(item)}>
                      <Text style={styles.secondaryText}>İçeriği ve geçmişini aç</Text>
                    </Pressable>
                  </View>
                ) : renderQueueItem(item))}
                {!items.length && !loading && <Text style={styles.muted}>Bu listede kayıt yok.</Text>}
                {cursor !== null && (
                  <Pressable accessibilityRole="button" disabled={loading} style={styles.secondary} onPress={() => void load(false)}>
                    <Text style={styles.secondaryText}>Daha fazla</Text>
                  </Pressable>
                )}
              </>
            )}
            {loading && <ActivityIndicator color={C.navy} style={{ margin: 12 }} />}
            <Pressable accessibilityRole="button" disabled={loading} style={styles.secondary} onPress={() => void load(true)}>
              <Text style={styles.secondaryText}>Listeyi yenile</Text>
            </Pressable>
          </>
        )}

        {!!notice && <Text accessibilityRole="alert" style={styles.notice}>{notice}</Text>}
        {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1, backgroundColor: C.bg },
  pad: { padding: 16, paddingBottom: 36 },
  title: { fontSize: 23, fontWeight: "900", color: C.navy, marginBottom: 8 },
  card: { backgroundColor: "#FFFFFF", borderWidth: 1, borderColor: C.line, borderRadius: 16, padding: 14, marginTop: 12 },
  cardTitle: { color: C.navy, fontSize: 16, fontWeight: "900", marginBottom: 5 },
  muted: { color: C.muted, fontSize: 12, lineHeight: 18, marginVertical: 4 },
  body: { color: C.text, fontSize: 14, lineHeight: 21, marginVertical: 8 },
  row: { flexDirection: "row", flexWrap: "wrap", alignItems: "center", gap: 8, marginVertical: 8 },
  chip: { paddingHorizontal: 12, paddingVertical: 9, borderRadius: 18, borderWidth: 1, borderColor: C.line, backgroundColor: "#FFFFFF", marginRight: 5, marginVertical: 3 },
  chipSelected: { backgroundColor: C.navy, borderColor: C.navy },
  chipText: { color: C.navy, fontSize: 12, fontWeight: "800" },
  chipTextSelected: { color: "#FFFFFF" },
  filterRow: { paddingVertical: 6 },
  primary: { minHeight: 46, padding: 13, borderRadius: 12, backgroundColor: C.navy, alignItems: "center", justifyContent: "center", marginTop: 10 },
  primaryText: { color: "#FFFFFF", fontSize: 14, fontWeight: "800" },
  secondary: { minHeight: 40, paddingHorizontal: 12, paddingVertical: 10, borderRadius: 10, backgroundColor: "#EEF3F8", alignItems: "center", justifyContent: "center", marginTop: 8 },
  secondaryText: { color: C.navy, fontSize: 12, fontWeight: "800" },
  disabled: { opacity: 0.45 },
  codeInput: { borderWidth: 1, borderColor: C.line, borderRadius: 12, backgroundColor: "#FFFFFF", padding: 14, marginTop: 12, color: C.text, fontSize: 22, letterSpacing: 8, textAlign: "center" },
  grantRow: { flexDirection: "row", alignItems: "center", gap: 8, backgroundColor: "#EAF6EF", borderRadius: 14, padding: 12, marginVertical: 12 },
  grantTitle: { color: C.green, fontWeight: "900", fontSize: 14 },
  input: { minHeight: 90, borderWidth: 1, borderColor: C.line, borderRadius: 12, padding: 12, backgroundColor: "#FFFFFF", color: C.text, textAlignVertical: "top", marginTop: 8 },
  sectionTitle: { color: C.navy, fontSize: 13, fontWeight: "900", marginTop: 14 },
  history: { color: C.muted, fontSize: 11, lineHeight: 17, marginTop: 5 },
  decision: { flexGrow: 1, backgroundColor: C.navy, paddingHorizontal: 12, paddingVertical: 12, borderRadius: 10, alignItems: "center", minWidth: 90 },
  decisionText: { color: "#FFFFFF", fontSize: 11, fontWeight: "800" },
  mediaGrid: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginVertical: 8 },
  media: { width: "48%", height: 150, borderRadius: 10, backgroundColor: C.bg },
  notice: { color: C.green, fontSize: 13, lineHeight: 18, marginTop: 12 },
  error: { color: C.red, fontSize: 13, lineHeight: 18, marginTop: 12 },
});
