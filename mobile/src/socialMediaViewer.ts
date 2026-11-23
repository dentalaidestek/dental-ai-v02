/**
 * Non-secret child-image key. Account/token rotation is handled by the
 * parent session-scoped viewer key; bearer credentials never belong in React keys.
 */
export function socialMediaRequestKey(mediaId: number | null, attempt: number): string {
  if (mediaId === null) return "empty";
  if (!Number.isSafeInteger(mediaId) || mediaId < 1 || !Number.isSafeInteger(attempt) || attempt < 0) {
    return "invalid";
  }
  return `media:${mediaId}:attempt:${attempt}`;
}

export type SocialMediaItem = { id: number; url: string };

export type SocialPan = { x: number; y: number };

export function normalizeSocialMediaItems(value: unknown): SocialMediaItem[] {
  if (!Array.isArray(value) || value.length > 4) return [];
  const result: SocialMediaItem[] = [];
  const seen = new Set<number>();
  for (const entry of value) {
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) return [];
    const item = entry as Record<string, unknown>;
    const id = item.id;
    const url = item.url;
    if (
      !Number.isSafeInteger(id) ||
      (id as number) < 1 ||
      typeof url !== "string" ||
      url !== `/api/expert-social/media/${id}` ||
      seen.has(id as number)
    ) {
      return [];
    }
    seen.add(id as number);
    result.push({ id: id as number, url });
  }
  return result;
}

export function clampSocialZoom(value: number): number {
  if (!Number.isFinite(value)) return 1;
  return Math.max(1, Math.min(5, value));
}

export function pinchSocialZoom(
  startZoom: number,
  startDistance: number,
  currentDistance: number,
): number {
  if (
    !Number.isFinite(startDistance) ||
    !Number.isFinite(currentDistance) ||
    startDistance <= 0 ||
    currentDistance <= 0
  ) {
    return clampSocialZoom(startZoom);
  }
  return clampSocialZoom(startZoom * (currentDistance / startDistance));
}

export function clampSocialPan(
  x: number,
  y: number,
  stageWidth: number,
  stageHeight: number,
  imageWidth: number,
  imageHeight: number,
  zoomValue: number,
): SocialPan {
  const zoom = clampSocialZoom(zoomValue);
  if (
    zoom <= 1 ||
    ![stageWidth, stageHeight, imageWidth, imageHeight].every(
      (value) => Number.isFinite(value) && value > 0,
    )
  ) {
    return { x: 0, y: 0 };
  }
  const fit = Math.min(stageWidth / imageWidth, stageHeight / imageHeight);
  const maxX = Math.max(0, (imageWidth * fit * zoom - stageWidth) / 2);
  const maxY = Math.max(0, (imageHeight * fit * zoom - stageHeight) / 2);
  const boundedX = Math.max(-maxX, Math.min(maxX, Number.isFinite(x) ? x : 0));
  const boundedY = Math.max(-maxY, Math.min(maxY, Number.isFinite(y) ? y : 0));
  return {
    x: boundedX === 0 ? 0 : boundedX,
    y: boundedY === 0 ? 0 : boundedY,
  };
}

export function socialSwipeDirection(
  dx: number,
  dy: number,
  zoomValue: number,
): -1 | 0 | 1 {
  if (
    clampSocialZoom(zoomValue) > 1 ||
    !Number.isFinite(dx) ||
    !Number.isFinite(dy) ||
    Math.abs(dx) < 60 ||
    Math.abs(dy) >= Math.abs(dx) * 0.7
  ) {
    return 0;
  }
  return dx < 0 ? 1 : -1;
}

export function nextSocialMediaIndex(
  index: number,
  delta: number,
  count: number,
): number | null {
  if (
    !Number.isSafeInteger(index) ||
    !Number.isSafeInteger(delta) ||
    !Number.isSafeInteger(count) ||
    count < 1 ||
    index < 0 ||
    index >= count
  ) {
    return null;
  }
  const next = index + delta;
  return next >= 0 && next < count ? next : null;
}
