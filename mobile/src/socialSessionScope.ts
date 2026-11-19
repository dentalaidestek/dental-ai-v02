export type SocialSessionIdentity = {
  userId: number;
  token: string;
};

/**
 * Opaque in-memory partition for session-owned feed state.
 * The bearer value is never persisted, rendered, logged or sent through this key.
 */
export function socialSessionKey(userId: number, token: string): string {
  return `${userId}:${token.length}:${token}`;
}

export function isSocialSessionCurrent(
  current: SocialSessionIdentity,
  expected: SocialSessionIdentity,
): boolean {
  return (
    current.userId === expected.userId &&
    current.token === expected.token
  );
}
