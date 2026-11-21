/** Opaque, process-local React identity. Never derive component keys from credentials. */
let sessionRenderSequence = 0;

export function nextSessionRenderKey(): string {
  sessionRenderSequence += 1;
  return `dai-session-${sessionRenderSequence.toString(36)}`;
}
