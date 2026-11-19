export type SocialSessionIdentity = {
  userId: number;
  token: string;
};

/**
 * A non-secret in-memory generation key for account-owned UI and page state.
 * The bearer token is compared separately and is never embedded in React keys.
 */
export function socialSessionKey(userId: number, generation: number): string {
  return `${userId}:${generation}`;
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
