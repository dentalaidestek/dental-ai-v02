import React, { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, AppState, Linking, Pressable, Text, View } from "react-native";
import { disableNativePush, enableNativePush, getNativePushState, NativePushState } from "./nativePush";

export default function NativePushSettings({ token, userId }: { token: string; userId: number }) {
  const [state, setState] = useState<NativePushState | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [mounted, setMounted] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const result = await getNativePushState(userId);
      if (mounted) setState(result);
    } catch (e) {
      if (mounted) setError(e instanceof Error ? e.message : "Bildirim ayarı okunamadı.");
    }
  }, [userId, mounted]);

  useEffect(() => {
    setMounted(true);
    void refresh();
    const listener = AppState.addEventListener("change", (value) => {
      if (value === "active") void refresh();
    });
    return () => {
      setMounted(false);
      listener.remove();
    };
  }, [refresh]);

  async function toggle() {
    if (busy || !state?.configured || !state.supported) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const next = state.enabled
        ? await disableNativePush(token, userId)
        : await enableNativePush(token, userId);
      setState(next);
      setNotice(next.enabled ? "Bu cihazda bildirimler açıldı." : "Bu cihazın bildirim kaydı kapatıldı.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Cihaz bildirimi ayarı tamamlanamadı.");
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  async function openSettings() {
    try {
      await Linking.openSettings();
    } catch {
      setError("Uygulama ayarları açılamadı. Telefonunuzun bildirim ayarlarını kullanın.");
    }
  }

  const buttonStyle = {
    minHeight: 48,
    borderRadius: 12,
    paddingHorizontal: 14,
    alignItems: "center" as const,
    justifyContent: "center" as const,
    backgroundColor: "#071B35",
    marginTop: 12,
    opacity: busy ? 0.55 : 1,
  };

  return (
    <View style={{ paddingTop: 4 }}>
      <Text style={{ color: "#53657B", lineHeight: 21 }}>
        {state?.enabled
          ? "Bu cihazda sistem bildirimleri açık."
          : "Sistem bildirimleri isteğe bağlıdır. İzin yalnızca aşağıdaki düğmeye bastığınızda istenir."}
      </Text>
      <Text style={{ color: "#718096", fontSize: 12, lineHeight: 18, marginTop: 8 }}>
        Kilit ekranında hasta adı, vaka metni veya klinik ayrıntı gönderilmez; yalnızca genel Dental AI bildirimi gösterilir.
      </Text>
      {state && !state.supported && (
        <Text style={{ color: "#B42318", marginTop: 10 }}>Bu cihaz platformunda sistem bildirimi desteklenmiyor.</Text>
      )}
      {state && state.supported && !state.configured && (
        <Text style={{ color: "#B42318", lineHeight: 20, marginTop: 10 }}>
          EAS proje kimliği yapılandırılmadığı için cihaz kaydı açılamıyor. Bu nedenle işletim sistemi izni istenmedi.
        </Text>
      )}
      {state?.permission === "denied" && !state.canAskAgain && state.configured && (
        <Pressable accessibilityRole="button" disabled={busy} onPress={() => void openSettings()} style={buttonStyle}>
          <Text style={{ color: "#FFF", fontWeight: "800" }}>Uygulama Ayarlarını Aç</Text>
        </Pressable>
      )}
      {state?.configured && state.supported && !(state.permission === "denied" && !state.canAskAgain) && (
        <Pressable accessibilityRole="button" accessibilityState={{ disabled: busy }} disabled={busy} onPress={() => void toggle()} style={buttonStyle}>
          {busy ? <ActivityIndicator color="#FFF" /> : <Text style={{ color: "#FFF", fontWeight: "800" }}>
            {state.enabled ? "Bu Cihazda Bildirimleri Kapat" : "Cihaz Bildirimlerini Aç"}
          </Text>}
        </Pressable>
      )}
      {!!error && <Text accessibilityRole="alert" style={{ color: "#B42318", lineHeight: 20, marginTop: 10 }}>{error}</Text>}
      {!!notice && <Text accessibilityRole="alert" style={{ color: "#16803C", lineHeight: 20, marginTop: 10 }}>{notice}</Text>}
    </View>
  );
}
