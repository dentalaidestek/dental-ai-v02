export type ModerationCandidate = {
  id: number;
  owned: boolean;
  status: string;
};

export const SOCIAL_MODERATION_RESUME_LIMIT = 5;
export const SOCIAL_MODERATION_RESUME_COOLDOWN_MS = 15_000;

export function selectOwnedModerationCandidates<T extends ModerationCandidate>(
  posts: readonly T[],
  limit = SOCIAL_MODERATION_RESUME_LIMIT,
): T[] {
  if (!Array.isArray(posts) || !Number.isSafeInteger(limit) || limit < 1) {
    return [];
  }
  const boundedLimit = Math.min(limit, SOCIAL_MODERATION_RESUME_LIMIT);
  return posts
    .filter(
      (post) =>
        post &&
        Number.isSafeInteger(post.id) &&
        post.id > 0 &&
        post.owned === true &&
        (post.status === "PENDING" || post.status === "REJECTED"),
    )
    .slice(0, boundedLimit);
}

export function isSocialAppResume(
  previous: string | null,
  next: string,
): boolean {
  return (
    next === "active" &&
    (previous === "background" || previous === "inactive")
  );
}

export function createModerationResumeGate(
  cooldownMs = SOCIAL_MODERATION_RESUME_COOLDOWN_MS,
): (now?: number) => boolean {
  const interval =
    Number.isFinite(cooldownMs) && cooldownMs >= 0
      ? Math.min(cooldownMs, 60_000)
      : SOCIAL_MODERATION_RESUME_COOLDOWN_MS;
  let lastAt: number | null = null;
  return (now = Date.now()) => {
    if (!Number.isFinite(now)) return false;
    if (lastAt !== null && now - lastAt < interval) return false;
    lastAt = now;
    return true;
  };
}
