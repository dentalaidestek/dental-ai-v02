/** Opaque, process-local React identity. Never derive component keys from credentials. */
let sessionRenderSequence = 0;

export function nextSessionRenderKey(): string {
  sessionRenderSequence += 1;
  return `dai-session-${sessionRenderSequence.toString(36)}`;
}

export type SessionRenderIdentity = Readonly<{scope:string;key:string}>;

/** Keep the credential-bearing scope private to a ref; expose only an opaque renderer key. */
export function resolveSessionRenderIdentity(
 current:SessionRenderIdentity|null,
 scope:string,
):SessionRenderIdentity{
 return current?.scope===scope?current:{scope,key:nextSessionRenderKey()};
}
