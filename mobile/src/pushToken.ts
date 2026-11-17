const EXPO_PUSH_TOKEN_PATTERN = /^(?:Expo|Exponent)PushToken\[[A-Za-z0-9_-]{8,128}\]$/;

/** Validate the canonical Expo token shape before requesting or storing a device registration. */
export function isValidExpoPushToken(value: unknown): value is string {
  return typeof value === "string" && EXPO_PUSH_TOKEN_PATTERN.test(value);
}
