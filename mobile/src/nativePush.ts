import { Platform } from "react-native";
import * as SecureStore from "expo-secure-store";
import * as Crypto from "expo-crypto";
import Constants from "expo-constants";
import * as Notifications from "expo-notifications";
import { claimPushDevice, registerPushDevice, unregisterPushDevice } from "./modernApi";
import { isValidExpoPushToken } from "./pushToken";
import { resolveExpoPushTarget, NativeNotificationTarget } from "./notificationTarget";

const DEVICE_ID_KEY = "dai.push.device_id";
const INSTALLATION_PROOF_KEY = "dai.push.installation_proof";
type DeviceIdentity = { deviceId: string; installationProof: string };
let deviceIdentityPromise: Promise<DeviceIdentity> | null = null;
let installationClaimQueue: Promise<void> = Promise.resolve();

// All server mutations for this physical installation share one ordered queue.
// In particular, logout must run after any in-flight login claim/refresh so a
// late claim cannot re-bind the device to an account that has already signed out.
function enqueueInstallationMutation<T>(operation: () => Promise<T>): Promise<T> {
  const result = installationClaimQueue.then(operation, operation);
  installationClaimQueue = result.then(() => undefined, () => undefined);
  return result;
}
const ENABLED_USER_KEY = (userId: number) => "dai.push.enabled." + String(userId);
const DELIVERY_USER_KEY = (userId: number) => "dai.push.delivery." + String(userId);


export type NativePushState = {
  supported: boolean;
  configured: boolean;
  enabled: boolean;
  deliveryEnabled: boolean;
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

async function storedDeviceId(): Promise<string | null> {
  const existing = (await SecureStore.getItemAsync(DEVICE_ID_KEY))?.trim();
  return existing && /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(existing)
    ? existing
    : null;
}

async function deviceIdentity(): Promise<DeviceIdentity> {
  if (!deviceIdentityPromise) {
    deviceIdentityPromise = (async () => {
      const existingId = await storedDeviceId();
      const deviceId = existingId || Crypto.randomUUID();
      if (!existingId) {
        await SecureStore.setItemAsync(DEVICE_ID_KEY, deviceId);
        await SecureStore.deleteItemAsync(INSTALLATION_PROOF_KEY);
      }

      let installationProof = await SecureStore.getItemAsync(INSTALLATION_PROOF_KEY);
      if (installationProof && !/^[0-9a-f]{64}$/.test(installationProof)) {
        throw new Error("Cihaz kurulum doğrulaması okunamadı. Güvenli bildirim kaydı yapılamadı.");
      }
      if (!installationProof) {
        const bytes = await Crypto.getRandomBytesAsync(32);
        installationProof = Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
        await SecureStore.setItemAsync(INSTALLATION_PROOF_KEY, installationProof);
      }
      return { deviceId, installationProof };
    })().catch((error) => {
      deviceIdentityPromise = null;
      throw error;
    });
  }
  return deviceIdentityPromise;
}

function enabledKey(userId: number): string {
  if (!Number.isSafeInteger(userId) || userId <= 0) throw new Error("Geçersiz hesap kimliği.");
  return ENABLED_USER_KEY(userId);
}

export async function getNativePushState(userId: number): Promise<NativePushState> {
  if (Platform.OS !== "android" && Platform.OS !== "ios") {
    return { supported: false, configured: false, enabled: false, deliveryEnabled: false, permission: "unsupported", canAskAgain: false };
  }
  const permission = await Notifications.getPermissionsAsync();
  const [optedIn, deliveryEnabled] = await Promise.all([
    SecureStore.getItemAsync(enabledKey(userId)),
    SecureStore.getItemAsync(DELIVERY_USER_KEY(userId)),
  ]);
  return {
    supported: true,
    configured: !!easProjectId(),
    enabled: optedIn === "1" && permission.granted,
    deliveryEnabled: optedIn === "1" && deliveryEnabled === "1",
    permission: permission.status,
    canAskAgain: permission.canAskAgain,
  };
}

async function expoToken(): Promise<{ deviceId: string; installationProof: string; token: string; platform: "android" | "ios" }> {
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
  if (!isValidExpoPushToken(result.data)) {
    throw new Error("Expo geçerli bir cihaz bildirim anahtarı döndürmedi.");
  }
  const identity = await deviceIdentity();
  return { ...identity, token: result.data, platform };
}

/** Called only from the explicit account setting; never prompts during app startup. */
export async function enableNativePush(token: string, userId: number): Promise<NativePushState> {
  await enqueueInstallationMutation(async () => {
    const registration = await expoToken();
    const registered = await registerPushDevice(token, registration.deviceId, registration.token, registration.platform, registration.installationProof);
    await SecureStore.setItemAsync(enabledKey(userId), "1");
    await SecureStore.setItemAsync(DELIVERY_USER_KEY(userId), registered.delivery_enabled ? "1" : "0");
  });
  return getNativePushState(userId);
}

/** Claim this installation for the authenticated account without enabling push or requesting OS permission. */
export function claimNativePushDeviceForSession(token: string, userId: number): Promise<void> {
  enabledKey(userId); // Validate the account scope before making the authenticated claim.
  return enqueueInstallationMutation(async () => {
    const identity = await deviceIdentity();
    await claimPushDevice(token, identity.deviceId, identity.installationProof);
  });
}

/** Refreshes an opted-in token on login/foreground without showing a permission prompt. */
export async function refreshNativePushRegistration(token: string, userId: number): Promise<boolean> {
  if ((await SecureStore.getItemAsync(enabledKey(userId))) !== "1") return false;
  return enqueueInstallationMutation(async () => {
    // Re-check after waiting: logout or an explicit opt-out may have run first.
    if ((await SecureStore.getItemAsync(enabledKey(userId))) !== "1") return false;
    const platform = Platform.OS;
    if (platform !== "android" && platform !== "ios") return false;

    const permission = await Notifications.getPermissionsAsync();
    const currentDeviceId = await storedDeviceId();
    if (!permission.granted) {
      if (currentDeviceId) await unregisterPushDevice(token, currentDeviceId);
      await SecureStore.deleteItemAsync(enabledKey(userId));
      await SecureStore.deleteItemAsync(DELIVERY_USER_KEY(userId));
      return false;
    }
    if (!easProjectId()) return false;

    const registration = await expoToken();
    const registered = await registerPushDevice(token, registration.deviceId, registration.token, registration.platform, registration.installationProof);
    await SecureStore.setItemAsync(DELIVERY_USER_KEY(userId), registered.delivery_enabled ? "1" : "0");
    return true;
  });
}

export async function disableNativePush(token: string, userId: number): Promise<NativePushState> {
  await enqueueInstallationMutation(async () => {
    const currentDeviceId = await storedDeviceId();
    if (currentDeviceId) await unregisterPushDevice(token, currentDeviceId);
    await SecureStore.deleteItemAsync(enabledKey(userId));
    await SecureStore.deleteItemAsync(DELIVERY_USER_KEY(userId));
  });
  return getNativePushState(userId);
}

/** Logout revokes this account/device pair after every earlier claim/refresh has settled. */
export async function unregisterNativePushForLogout(token: string, userId: number): Promise<void> {
  await enqueueInstallationMutation(async () => {
    const currentDeviceId = await storedDeviceId();
    if (currentDeviceId) await unregisterPushDevice(token, currentDeviceId);
    await SecureStore.deleteItemAsync(enabledKey(userId));
    await SecureStore.deleteItemAsync(DELIVERY_USER_KEY(userId));
  });
}

export function subscribeToNativePushResponses(
  onTarget: (target: NativeNotificationTarget) => void,
): () => void {
  const handled = new Set<string>();
  const handle = (response: Notifications.NotificationResponse) => {
    const identifier = response.notification.request.identifier;
    if (identifier && handled.has(identifier)) return;
    if (identifier) {
      handled.add(identifier);
      // Suppress only the listener/cold-start duplicate; a later deliberate
      // tap on the same notification must be allowed to navigate again.
      setTimeout(() => handled.delete(identifier), 1200);
    }

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
