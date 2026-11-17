import { Platform } from "react-native";
import * as SecureStore from "expo-secure-store";
import * as Crypto from "expo-crypto";
import Constants from "expo-constants";
import * as Notifications from "expo-notifications";
import { registerPushDevice, unregisterPushDevice } from "./modernApi";
import { resolveExpoPushTarget, NativeNotificationTarget } from "./notificationTarget";

const DEVICE_ID_KEY = "dai.push.device_id";
const ENABLED_USER_KEY = (userId: number) => "dai.push.enabled." + String(userId);
const EXPO_TOKEN_PATTERN = /^(?:Expo|Exponent)PushToken\\[[A-Za-z0-9_-]{8,128}\\]$/;

export type NativePushState = {
  supported: boolean;
  configured: boolean;
  enabled: boolean;
  permission: string;
  canAskAgain: boolean;
};

function platformName(): "android" | "ios" {
  if (Platform.OS !== "android" && Platform.OS !== "ios") {
    throw new Error("Cihaz bildirimleri yalnızca Android ve iOS uygulamalarında kullanılabilir.");
  }
  return Platform.OS;
}

function easProjectId(): string {
  const extra = Constants.expoConfig?.extra as { eas?: { projectId?: string } } | undefined;
  const configured = extra?.eas?.projectId || Constants.easConfig?.projectId || "";
  return typeof configured === "string" ? configured.trim() : "";
}

async function deviceId(): Promise<string> {
  const existing = (await SecureStore.getItemAsync(DEVICE_ID_KEY))?.trim();
  if (existing && /^[0-9a-f-]{36}$/i.test(existing)) return existing;
  const created = Crypto.randomUUID();
  await SecureStore.setItemAsync(DEVICE_ID_KEY, created);
  return created;
}

function enabledKey(userId: number): string {
  if (!Number.isSafeInteger(userId) || userId <= 0) throw new Error("Geçersiz hesap kimliği.");
  return ENABLED_USER_KEY(userId);
}

export async function getNativePushState(userId: number): Promise<NativePushState> {
  if (Platform.OS !== "android" && Platform.OS !== "ios") {
    return { supported: false, configured: false, enabled: false, permission: "unsupported", canAskAgain: false };
  }
  const permission = await Notifications.getPermissionsAsync();
  const optedIn = (await SecureStore.getItemAsync(enabledKey(userId))) === "1";
  return {
    supported: true,
    configured: !!easProjectId(),
    enabled: optedIn && permission.granted,
    permission: permission.status,
    canAskAgain: permission.canAskAgain,
  };
}

async function expoToken(): Promise<{ deviceId: string; token: string; platform: "android" | "ios" }> {
  const platform = platformName();
  const projectId = easProjectId();
  if (!projectId) {
    throw new Error("Cihaz bildirimi kaydı için EXPO_PUBLIC_EAS_PROJECT_ID yapılandırılmamış. Güvenlik nedeniyle izin istenmedi.");
  }

  let permission = await Notifications.getPermissionsAsync();
  if (!permission.granted) permission = await Notifications.requestPermissionsAsync();
  if (!permission.granted) {
    throw new Error(permission.canAskAgain
      ? "Cihaz bildirimi izni verilmedi."
      : "Bildirim izni kapalı. Uygulama ayarlarından izin vermeniz gerekiyor.");
  }

  if (platform === "android") {
    await Notifications.setNotificationChannelAsync("default", {
      name: "Dental AI",
      importance: Notifications.AndroidImportance.DEFAULT,
      sound: "default",
      vibrationPattern: [0, 250, 250, 250],
      lightColor: "#071B35",
    });
  }

  const result = await Notifications.getExpoPushTokenAsync({ projectId });
  if (!EXPO_TOKEN_PATTERN.test(result.data)) {
    throw new Error("Expo geçerli bir cihaz bildirim anahtarı döndürmedi.");
  }
  return { deviceId: await deviceId(), token: result.data, platform };
}

/** Called only from the explicit account setting; never prompts during app startup. */
export async function enableNativePush(token: string, userId: number): Promise<NativePushState> {
  const registration = await expoToken();
  await registerPushDevice(token, registration.deviceId, registration.token, registration.platform);
  await SecureStore.setItemAsync(enabledKey(userId), "1");
  return getNativePushState(userId);
}

/** Refreshes an opted-in token on login/foreground without showing a permission prompt. */
export async function refreshNativePushRegistration(token: string, userId: number): Promise<boolean> {
  if ((await SecureStore.getItemAsync(enabledKey(userId))) !== "1") return false;
  const platform = Platform.OS;
  if (platform !== "android" && platform !== "ios") return false;

  const permission = await Notifications.getPermissionsAsync();
  const currentDeviceId = await SecureStore.getItemAsync(DEVICE_ID_KEY);
  if (!permission.granted) {
    if (currentDeviceId) await unregisterPushDevice(token, currentDeviceId);
    await SecureStore.deleteItemAsync(enabledKey(userId));
    return false;
  }
  if (!easProjectId()) return false;

  const registration = await expoToken();
  await registerPushDevice(token, registration.deviceId, registration.token, registration.platform);
  return true;
}

export async function disableNativePush(token: string, userId: number): Promise<NativePushState> {
  const currentDeviceId = await SecureStore.getItemAsync(DEVICE_ID_KEY);
  if (currentDeviceId) await unregisterPushDevice(token, currentDeviceId);
  await SecureStore.deleteItemAsync(enabledKey(userId));
  return getNativePushState(userId);
}

/** Logout revokes this account/device pair before the session is discarded. */
export async function unregisterNativePushForLogout(token: string, userId: number): Promise<void> {
  const currentDeviceId = await SecureStore.getItemAsync(DEVICE_ID_KEY);
  if (currentDeviceId) await unregisterPushDevice(token, currentDeviceId);
  await SecureStore.deleteItemAsync(enabledKey(userId));
}

export function subscribeToNativePushResponses(
  onTarget: (target: NativeNotificationTarget) => void,
): () => void {
  const handled = new Set<string>();
  const handle = (response: Notifications.NotificationResponse) => {
    const identifier = response.notification.request.identifier;
    if (identifier && handled.has(identifier)) return;
    if (identifier) handled.add(identifier);

    const target = resolveExpoPushTarget(response.notification.request.content.data);
    if (target.kind === "navigate") onTarget(target);
    try {
      Notifications.clearLastNotificationResponse();
    } catch {
      // Some older native clients do not expose the clear method; in-memory
      // de-duplication still prevents listener/cold-start double navigation.
    }
  };

  const subscription = Notifications.addNotificationResponseReceivedListener(handle);
  void Notifications.getLastNotificationResponseAsync().then((response) => {
    if (response) handle(response);
  }).catch(() => undefined);

  return () => subscription.remove();
}

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: false,
    shouldSetBadge: false,
  }),
});
