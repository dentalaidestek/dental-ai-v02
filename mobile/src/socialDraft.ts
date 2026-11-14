import { ApiError } from "./api";
// Save intent before sending. An uncertain response retains the exact same UUID
// and payload; both platforms and web deduplicate on the server's UUID constraint.
export type Draft = {
  id: string;
  text: string;
  link: string;
  media_ids: number[];
  attempted: boolean;
};
export type DraftStore = {
  getItemAsync(k: string): Promise<string | null>;
  setItemAsync(k: string, v: string): Promise<void>;
  deleteItemAsync(k: string): Promise<void>;
};
// Keychain implementations can reject large individual values. Publish a small
// manifest only after all encrypted chunks exist; failed writes retain the old
// manifest. Legacy single-value drafts remain readable.
export function chunkedDraftStore(
  raw: DraftStore,
  unique: () => string,
  maxChunks = 100,
): DraftStore {
  if(!Number.isInteger(maxChunks)||maxChunks<1||maxChunks>512)throw Error("Geçersiz güvenli taslak sınırı.");
  const pending = new Map<string, Promise<unknown>>();
  function serial<T>(key: string, work: () => Promise<T>): Promise<T> {
    const run = (pending.get(key) || Promise.resolve())
      .catch(() => {})
      .then(work);
    pending.set(key, run);
    const clear = () => {
      if (pending.get(key) === run) pending.delete(key);
    };
    run.then(clear, clear);
    return run;
  }
  const manifest = (
    value: string | null,
  ): { chunks: number; revision: string } | null => {
    if (!value) return null;
    try {
      const v = JSON.parse(value);
      return Number.isInteger(v.chunks) &&
        v.chunks > 0 &&
        v.chunks <= maxChunks &&
        typeof v.revision === "string"
        ? v
        : null;
    } catch {
      return null;
    }
  };
  const remove = async (
    key: string,
    m: { chunks: number; revision: string } | null,
  ) => {
    if (m)
      await Promise.all(
        Array.from({ length: m.chunks }, (_, i) =>
          raw.deleteItemAsync(`${key}.${m.revision}.${i}`).catch(() => {}),
        ),
      );
  };
  return {
    getItemAsync(key) {
      return serial(key, async () => {
        const value = await raw.getItemAsync(key),
          m = manifest(value);
        if (!m) return value;
        const parts = await Promise.all(
          Array.from({ length: m.chunks }, (_, i) =>
            raw.getItemAsync(`${key}.${m.revision}.${i}`),
          ),
        );
        if (parts.some((v) => v === null))
          throw Error("Taslağın bir parçası okunamadı.");
        return parts.join("");
      });
    },
    setItemAsync(key, value) {
      return serial(key, async () => {
        const old = manifest(await raw.getItemAsync(key));
        const chars = Array.from(value),
          parts: string[] = [];
        for (let i = 0; i < chars.length; i += 300)
          parts.push(chars.slice(i, i + 300).join(""));
        if (!parts.length) parts.push("");
        if(parts.length>maxChunks)throw Error("Taslak güvenli depolama sınırını aşıyor.");
        const next = { revision: unique(), chunks: parts.length };
        try {
          for (let i = 0; i < parts.length; i++)
            await raw.setItemAsync(`${key}.${next.revision}.${i}`, parts[i]);
          await raw.setItemAsync(key, JSON.stringify(next));
        } catch (e) {
          await remove(key, next);
          throw e;
        }
        await remove(key, old);
      });
    },
    deleteItemAsync(key) {
      return serial(key, async () => {
        const old = manifest(await raw.getItemAsync(key));
        await raw.deleteItemAsync(key);
        await remove(key, old);
      });
    },
  };
}
export function draftKey(userId: number, scope: string) {
  return `dai.social.${userId}.${scope}`;
}
export async function readDraft(
  store: DraftStore,
  key: string,
): Promise<Draft | null> {
  const value = await store.getItemAsync(key);
  if (!value) return null;
  const d = JSON.parse(value);
  if (
    typeof d.id !== "string" ||
    typeof d.text !== "string" ||
    typeof d.link !== "string" ||
    !Array.isArray(d.media_ids)
  )
    throw new Error("Taslak okunamadı.");
  return d;
}
export async function submitDraft<T>(
  store: DraftStore,
  key: string,
  draft: Draft,
  send: (d: Draft) => Promise<T>,
): Promise<T> {
  const intent = { ...draft, attempted: true };
  await store.setItemAsync(key, JSON.stringify(intent));
  let result: T;
  try {
    result = await send(intent);
  } catch (error) {
    if (
      error instanceof ApiError &&
      [400, 403, 404, 413, 422, 429].includes(error.status)
    )
      await store.setItemAsync(
        key,
        JSON.stringify({ ...intent, attempted: false }),
      );
    throw error;
  }
  await store.deleteItemAsync(key);
  return result;
}
