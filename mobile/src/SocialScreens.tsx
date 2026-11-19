import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  AppState,
  FlatList,
  Image,
  KeyboardAvoidingView,
  Linking,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  Share,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import * as SecureStore from "expo-secure-store";
import * as Crypto from "expo-crypto";
import * as ImagePicker from "expo-image-picker";
import { User } from "./api";
import * as api from "./socialApi";
import {
  Draft,
  draftKey,
  readDraft,
  submitDraft,
  chunkedDraftStore,
} from "./socialDraft";
import { usePagedRecords } from "./usePagedRecords";
import {
  createModerationResumeGate,
  isSocialAppResume,
  selectOwnedModerationCandidates,
} from "./socialModerationRefresh";
import NativeSocialMediaViewer from "./NativeSocialMediaViewer";
import { socialSessionKey, isSocialSessionCurrent } from "./socialSessionScope";

const C = {
  navy: "#071B35",
  bg: "#F5F7FA",
  text: "#102033",
  muted: "#52647B",
  line: "#E5EAF0",
};
const message = (e: unknown) =>
  e instanceof Error ? e.message : "İşlem tamamlanamadı.";
const fresh = (): Draft => ({
  id: Crypto.randomUUID(),
  text: "",
  link: "",
  media_ids: [],
  attempted: false,
  preview_id: undefined,
  preview: null,
});
const draftStore = chunkedDraftStore(SecureStore, () => Crypto.randomUUID());
function Button({
  title,
  onPress,
  disabled = false,
}: {
  title: string;
  onPress: () => void;
  disabled?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      disabled={disabled}
      onPress={onPress}
      style={[s.button, disabled && { opacity: 0.45 }]}
    >
      <Text style={s.buttonText}>{title}</Text>
    </Pressable>
  );
}
function useDraft(userId: number, scope: string) {
  const key = draftKey(userId, scope),
    [draft, setDraft] = useState<Draft>(fresh),
    [ready, setReady] = useState(false),
    [retry, setRetry] = useState(0),
    [error, setError] = useState("");
  const queue = useRef(Promise.resolve()),
    current = useRef(draft);
  current.current = draft;
  useEffect(() => {
    let active = true;
    readDraft(draftStore, key)
      .then((d) => {
        if (active) {
          if (d) setDraft(d);
          setReady(true);
        }
      })
      .catch((e) => {
        if (active) setError(message(e));
      });
    return () => {
      active = false;
    };
  }, [key, retry]);
  const update = (patch: Partial<Draft>) => {
    const next = { ...current.current, ...patch };
    current.current = next;
    setDraft(next);
    queue.current = queue.current
      .catch(() => {})
      .then(() => {
        if (current.current === next)
          return draftStore.setItemAsync(key, JSON.stringify(next));
      });
    queue.current
      .then(() => setError(""))
      .catch((e) => setError("Taslak kaydedilemedi: " + message(e)));
  };
  const clear = async () => {
    await queue.current.catch(() => {});
    await draftStore.deleteItemAsync(key);
    const next = fresh();
    current.current = next;
    setDraft(next);
    setError("");
    setReady(true);
  };
  const send = async <T,>(fn: (d: Draft) => Promise<T>) => {
    await queue.current;
    const snapshot = { ...current.current, attempted: true };
    current.current = snapshot;
    setDraft(snapshot);
    let result: T;
    try {
      result = await submitDraft(draftStore, key, snapshot, fn);
    } catch (e) {
      const saved = await readDraft(draftStore, key);
      if (saved) {
        current.current = saved;
        setDraft(saved);
      }
      throw e;
    }
    const next = fresh();
    current.current = next;
    setDraft(next);
    return result;
  };
  return { draft, ready, error, retryRead: () => { setError(""); setRetry(v => v + 1); }, update, flush: () => queue.current, clear, send };
}

function Composer({
  token,
  userId,
  onClose,
  onPosted,
}: {
  token: string;
  userId: number;
  onClose: () => void;
  onPosted: (p: api.SocialPost) => void;
}) {
  const d = useDraft(userId, "post"),
    [busy, setBusy] = useState(false),
    [previewBusy, setPreviewBusy] = useState(false),
    [error, setError] = useState(""),
    previewGeneration = useRef(0),
    lock = useRef(false);
  const selectedCoverId =
    d.draft.link.trim().length > 0 &&
    typeof d.draft.cover_media_id === "number" &&
    Number.isSafeInteger(d.draft.cover_media_id) &&
    d.draft.media_ids.includes(d.draft.cover_media_id)
      ? d.draft.cover_media_id
      : undefined;
  const previewCoverUrl = selectedCoverId
    ? `/api/expert-social/media/${selectedCoverId}`
    : d.draft.preview?.cover?.url;

  useEffect(() => () => {
    previewGeneration.current++;
  }, []);

  async function image() {
    if (lock.current || d.draft.attempted) return;
    const remaining = Math.max(0, 4 - d.draft.media_ids.length);
    if (!remaining) return;
    lock.current = true;
    setBusy(true);
    setError("");
    try {
      const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!permission.granted) throw Error("Fotoğraf izni verilmedi.");
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ["images"],
        quality: 0.8,
        allowsMultipleSelection: true,
        selectionLimit: remaining,
      });
      if (result.canceled) return;
      let ids = [...d.draft.media_ids];
      for (const asset of result.assets || []) {
        if (ids.length >= 4) break;
        const mime = asset.mimeType || "image/jpeg";
        if (!["image/jpeg", "image/png", "image/webp"].includes(mime)) {
          setError("JPEG, PNG veya WebP görselleri seçin.");
          continue;
        }
        if (typeof asset.fileSize === "number" && asset.fileSize > 8 * 1024 * 1024) {
          setError("Her görsel en fazla 8 MB olabilir.");
          continue;
        }
        const extension =
          mime === "image/png" ? "png" : mime === "image/webp" ? "webp" : "jpg";
        const uploaded = await api.uploadSocialImage(token, {
          uri: asset.uri,
          name: asset.fileName || "social." + extension,
          type: mime,
        });
        if (!Number.isSafeInteger(uploaded.id) || uploaded.id < 1)
          throw Error("Yüklenen görselin kimliği doğrulanamadı.");
        ids = [...ids, uploaded.id];
        d.update({ media_ids: ids });
        // Persist each completed upload before starting the next one. A process
        // death cannot lose an already returned media ID from the draft.
        await d.flush();
      }
    } catch (e) {
      setError(message(e));
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }

  async function saveMediaIds(ids: number[]) {
    if (lock.current || d.draft.attempted) return;
    lock.current = true;
    setBusy(true);
    setError("");
    try {
      d.update({
        media_ids: ids,
        ...(d.draft.cover_media_id !== undefined &&
        !ids.includes(d.draft.cover_media_id)
          ? { cover_media_id: undefined }
          : {}),
      });
      await d.flush();
    } catch (e) {
      setError("Görsel taslağı kaydedilemedi: " + message(e));
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }

  async function previewLink() {
    if (lock.current || previewBusy) return;
    const url = d.draft.link.trim();
    try {
      const parsed = new URL(url);
      if (parsed.protocol !== "https:" || !parsed.hostname) throw new Error();
    } catch {
      setError("Geçerli bir HTTPS bağlantısı girin.");
      return;
    }
    const request = ++previewGeneration.current;
    setPreviewBusy(true);
    setError("");
    try {
      const preview = await api.getLinkPreview(token, url);
      if (request !== previewGeneration.current) return;
      const nextLink = preview.url || url;
      if (preview.available && preview.id) {
        d.update({ link: nextLink, preview_id: preview.id, preview });
        await d.flush();
      } else {
        d.update({ link: nextLink, preview_id: undefined, preview: null });
        await d.flush();
        setError(
          preview.message ||
            "Önizleme alınamadı. Bağlantıyı önizlemesiz paylaşabilirsiniz.",
        );
      }
    } catch (e) {
      if (request === previewGeneration.current) setError(message(e));
    } finally {
      if (request === previewGeneration.current) setPreviewBusy(false);
    }
  }

  async function post() {
    if (lock.current || previewBusy || d.draft.attempted) return;
    lock.current = true;
    setBusy(true);
    setError("");
    try {
      const p = await d.send((v) => {
        const coverMediaId = v.link.trim()
          ? typeof v.cover_media_id === "number" &&
            Number.isSafeInteger(v.cover_media_id) &&
            v.media_ids.includes(v.cover_media_id)
            ? v.cover_media_id
            : v.media_ids.length === 4
              ? v.media_ids[0]
              : undefined
          : undefined;
        return api.createPost(token, {
          text: v.text,
          media_ids: v.media_ids,
          idempotency_key: v.id,
          ...(v.link.trim() ? { link_url: v.link.trim() } : {}),
          ...(v.preview_id ? { preview_id: v.preview_id } : {}),
          ...(coverMediaId ? { cover_media_id: coverMediaId } : {}),
        });
      });
      onPosted(p);
      onClose();
    } catch (e) {
      setError(message(e));
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }

  function movePhoto(index: number, direction: -1 | 1) {
    const next = [...d.draft.media_ids];
    const target = index + direction;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    void saveMediaIds(next);
  }

  function removePhoto(id: number) {
    void saveMediaIds(d.draft.media_ids.filter((value) => value !== id));
  }

  return (
    <Sheet
      title="Gönderi paylaş"
      onClose={() => {
        if (!lock.current) {
          previewGeneration.current++;
          onClose();
        }
      }}
    >
      <ScrollView
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={s.pad}
      >
        <Text style={s.meta}>
          Paylaşım doğrulanmış uzman hesapları içindir. Hasta kimliği ve izinsiz
          klinik görüntü paylaşmayın.
        </Text>
        {!d.ready ? (
          <View>
            <ActivityIndicator />
            <Text style={s.error}>{d.error}</Text>
            {!!d.error && (
              <Button title="Tekrar oku" onPress={d.retryRead} />
            )}
            {!!d.error && (
              <Button
                title="Bozuk taslağı temizle"
                onPress={() => {
                  previewGeneration.current++;
                  void d.clear().catch((e) => setError(message(e)));
                }}
              />
            )}
          </View>
        ) : (
          <>
            <TextInput
              accessibilityLabel="Gönderi metni"
              placeholder="Meslektaşlarınla paylaş…"
              multiline
              maxLength={5000}
              editable={!busy && !d.draft.attempted}
              value={d.draft.text}
              onChangeText={(text) => d.update({ text })}
              style={[s.input, { minHeight: 140 }]}
            />
            <TextInput
              accessibilityLabel="Bağlantı"
              placeholder="https://… (isteğe bağlı)"
              autoCapitalize="none"
              keyboardType="url"
              editable={!busy && !d.draft.attempted}
              value={d.draft.link}
              onChangeText={(link) => {
                previewGeneration.current++;
                setPreviewBusy(false);
                d.update({
                  link,
                  preview_id: undefined,
                  preview: null,
                  ...(link.trim() ? {} : { cover_media_id: undefined }),
                });
              }}
              style={s.input}
            />
            <Button
              title={previewBusy ? "Önizleme alınıyor…" : d.draft.preview_id ? "Önizlemeyi yenile" : "Önizlemeyi getir"}
              onPress={() => void previewLink()}
              disabled={busy || previewBusy || d.draft.attempted || !d.draft.link.trim()}
            />
            {d.draft.link.trim() && (
              <Pressable
                accessibilityRole="link"
                accessibilityLabel="Bağlantı önizlemesini aç"
                onPress={() => {
                  try {
                    const parsed = new URL(d.draft.link);
                    if (
                      parsed.protocol !== "https:" ||
                      !parsed.hostname ||
                      parsed.username ||
                      parsed.password ||
                      (parsed.port && parsed.port !== "443")
                    )
                      throw new Error();
                    void Linking.openURL(parsed.href).catch((e) =>
                      setError(message(e)),
                    );
                  } catch {
                    setError("Güvenli HTTPS bağlantısı açılamadı.");
                  }
                }}
                style={s.previewCard}
              >
                {previewCoverUrl && (
                  <Image
                    source={api.socialImageSource(previewCoverUrl, token)}
                    style={s.previewImage}
                    resizeMode="cover"
                  />
                )}
                <View style={{ flex: 1 }}>
                  <Text style={s.previewTitle}>
                    {d.draft.preview?.title ||
                      d.draft.preview?.site_name ||
                      d.draft.preview?.domain ||
                      d.draft.link}
                  </Text>
                  {!!d.draft.preview?.domain && (
                    <Text style={s.previewMeta}>{d.draft.preview.domain}</Text>
                  )}
                  {!!d.draft.preview?.description && (
                    <Text style={s.previewDescription} numberOfLines={3}>
                      {d.draft.preview.description}
                    </Text>
                  )}
                </View>
              </Pressable>
            )}
            <Text style={s.meta}>{d.draft.media_ids.length}/4 fotoğraf</Text>
            {d.draft.link.trim() && d.draft.media_ids.length === 4 && !selectedCoverId && (
              <Text style={s.meta}>
                Dört görsel yüklendiğinde ilk görsel otomatik bağlantı kapağı olur.
              </Text>
            )}
            {d.draft.media_ids.length > 0 && (
              <View style={s.mediaGrid}>
                {d.draft.media_ids.map((id, index) => (
                  <View key={id} style={s.mediaItem}>
                    <Image
                      accessibilityLabel={`Yüklenen fotoğraf ${index + 1}`}
                      source={api.socialImageSource(
                        `/api/expert-social/media/${id}`,
                        token,
                      )}
                      resizeMode="cover"
                      style={s.mediaImage}
                    />
                    <View style={s.mediaControls}>
                      <Pressable
                        accessibilityRole="button"
                        accessibilityLabel={`Fotoğrafı önceye taşı ${index + 1}`}
                        disabled={busy || d.draft.attempted || index === 0}
                        onPress={() => movePhoto(index, -1)}
                        style={s.mediaControl}
                      >
                        <Text style={s.mediaControlText}>‹</Text>
                      </Pressable>
                      <Pressable
                        accessibilityRole="button"
                        accessibilityLabel={`Fotoğrafı kaldır ${index + 1}`}
                        disabled={busy || d.draft.attempted}
                        onPress={() => removePhoto(id)}
                        style={s.mediaControl}
                      >
                        <Text style={s.mediaControlText}>×</Text>
                      </Pressable>
                      <Pressable
                        accessibilityRole="button"
                        accessibilityLabel={`Fotoğrafı sonraya taşı ${index + 1}`}
                        disabled={busy || d.draft.attempted || index === d.draft.media_ids.length - 1}
                        onPress={() => movePhoto(index, 1)}
                        style={s.mediaControl}
                      >
                        <Text style={s.mediaControlText}>›</Text>
                      </Pressable>
                    </View>
                    {d.draft.link.trim() && (
                      <Pressable
                        accessibilityRole="button"
                        accessibilityLabel={
                          selectedCoverId === id
                            ? `Bağlantı kapağı seçildi ${index + 1}`
                            : `Bağlantı kapağı yap ${index + 1}`
                        }
                        accessibilityState={{ selected: selectedCoverId === id }}
                        disabled={busy || d.draft.attempted}
                        onPress={() =>
                          d.update({
                            cover_media_id: selectedCoverId === id ? undefined : id,
                          })
                        }
                        style={[
                          s.coverControl,
                          selectedCoverId === id && s.coverControlSelected,
                        ]}
                      >
                        <Text
                          style={[
                            s.coverControlText,
                            selectedCoverId === id && s.coverControlTextSelected,
                          ]}
                        >
                          {selectedCoverId === id ? "Bağlantı kapağı" : "Kapak yap"}
                        </Text>
                      </Pressable>
                    )}
                  </View>
                ))}
              </View>
            )}
            <Button
              title="Fotoğraf ekle"
              onPress={() => void image()}
              disabled={
                busy || d.draft.attempted || d.draft.media_ids.length >= 4
              }
            />
            {d.draft.attempted && (
              <Text style={s.meta}>
                Önceki gönderimin yanıtı alınamadı. Aynı paylaşımı güvenle
                tekrar deneyebilir veya taslağı silebilirsiniz.
              </Text>
            )}
            <Text style={s.error}>{error || d.error}</Text>
            <Button
              title={
                busy
                  ? "Gönderiliyor…"
                  : d.draft.attempted
                    ? "Tekrar dene"
                    : "Paylaş"
              }
              onPress={() => void post()}
              disabled={
                busy ||
                previewBusy ||
                (!d.draft.text.trim() &&
                  !d.draft.media_ids.length &&
                  !d.draft.link.trim())
              }
            />
            <Button
              title="Taslağı sil"
              disabled={busy}
              onPress={() =>
                Alert.alert(
                  "Taslak silinsin mi?",
                  "Gönderim daha önce sunucuya ulaştıysa gönderi profilinizde bulunabilir.",
                  [
                    { text: "Vazgeç" },
                    {
                      text: "Sil",
                      style: "destructive",
                      onPress: () => {
                        previewGeneration.current++;
                        void d.clear().catch((e) => setError(message(e)));
                      },
                    },
                  ],
                )
              }
            />
          </>
        )}
      </ScrollView>
    </Sheet>
  );
}
function Sheet({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <Modal animationType="slide" presentationStyle="fullScreen" onRequestClose={onClose} statusBarTranslucent={false}>
      <SafeAreaView style={[s.page, {flex:1}]}>
        <View style={s.header}>
          <Text style={s.title}>{title}</Text>
          <Pressable
            accessibilityLabel="Pencereyi kapat"
            accessibilityRole="button"
            hitSlop={12}
            onPress={onClose}
          >
            <Text style={s.action}>Kapat</Text>
          </Pressable>
        </View>
        <KeyboardAvoidingView
          style={{ flex: 1 }}
          behavior={Platform.OS === "ios" ? "padding" : "height"}
        >
          {children}
        </KeyboardAvoidingView>
      </SafeAreaView>
    </Modal>
  );
}

function CommentThread({
  token,
  item,
  postId,
  onChange,
  onReply,
  onProfile,
}: {
  token: string;
  item: api.SocialComment;
  postId: number;
  onChange: (c: api.SocialComment | null, id: number) => void;
  onReply: (id: number) => void;
  onProfile: (id: number, name: string) => void;
}) {
  const [editing, setEditing] = useState(false),
    [editText, setEditText] = useState(item.text);
  const [open, setOpen] = useState(false),
    [replies, setReplies] = useState<api.SocialComment[]>([]),
    [next, setNext] = useState<number | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const replyGeneration = useRef(0), replyLock = useRef(false), commentEditLock = useRef(false), commentDeleteLock = useRef(false);
  useEffect(() => {
    replyGeneration.current++;
    replyLock.current = false;
    setBusy(false);
    setReplies([]);
    setNext(null);
    setOpen(false);
    return () => {
      replyGeneration.current++;
      replyLock.current = false;
    };
  }, [token, postId, item.id, item.reply_count]);
  async function more() {
    if (replyLock.current) return;
    replyLock.current = true;
    const request = replyGeneration.current;
    setBusy(true);
    try {
      const page = await api.getComments(token, postId, next || 0, item.id);
      if (request !== replyGeneration.current) return;
      setReplies((v) => [
        ...v,
        ...page.items.filter((x) => !v.some((y) => y.id === x.id)),
      ]);
      // Reply cursors advance by comment ID; reject repeated or invalid pages.
      setNext(
        page.next_cursor !== null &&
        Number.isSafeInteger(page.next_cursor) &&
        page.next_cursor > 0 &&
        (!next || page.next_cursor > next)
          ? page.next_cursor
          : null,
      );
      setOpen(true);
    } catch (e) {
      if (request === replyGeneration.current) setError(message(e));
    } finally {
      if (request === replyGeneration.current) {
        replyLock.current = false;
        setBusy(false);
      }
    }
  }
  async function like() {
    if (busy) return;
    setBusy(true);
    try {
      const result = await api.setCommentLike(token, item.id, !item.liked);
      onChange({ ...item, ...result }, item.id);
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }
  function menu() {
    Alert.alert(
      "Yorum işlemleri",
      "",
      item.owned
        ? [
            { text: "Vazgeç" },
            {
              text: "Düzenle",
              onPress: () => {
                setEditText(item.text);
                setEditing(true);
              },
            },
            {
              text: "Sil",
              style: "destructive",
              onPress: () => {
                Alert.alert("Yorum silinsin mi?", "Bu işlem geri alınamaz.", [
                  { text: "Vazgeç", style: "cancel" },
                  {
                    text: "Sil",
                    style: "destructive",
                    onPress: async () => {
                      if (commentDeleteLock.current) return;
                      commentDeleteLock.current = true;
                      setBusy(true);
                      try {
                        await api.deleteComment(token, item.id);
                        onChange(null, item.id);
                      } catch (e) {
                        setError(message(e));
                      } finally {
                        commentDeleteLock.current = false;
                        setBusy(false);
                      }
                    },
                  },
                ]);
              },
            },
          ]
        : [
            { text: "Vazgeç" },
            {
              text: "Bildir",
              onPress: () => {
                api
                  .reportSocial(token, "COMMENT", item.id)
                  .then(() => Alert.alert("Bildirim alındı"))
                  .catch((e) => setError(message(e)));
              },
            },
          ],
    );
  }
  return (
    <View style={s.comment}>
      <View style={s.row}>
        <Pressable
          onPress={() =>
            item.author_verified && onProfile(item.author_id, item.author_name)
          }
          style={{ flex: 1 }}
        >
          <Text style={s.author}>{item.author_name}</Text>
        </Pressable>
        <Pressable accessibilityLabel="Yorum işlemleri" onPress={menu}>
          <Text style={s.action}>•••</Text>
        </Pressable>
      </View>
      <Text selectable style={s.body}>
        {item.text}
      </Text>
      {item.status !== "PUBLISHED" && (
        <Text style={s.meta}>İnceleme durumu: {item.status}</Text>
      )}
      <View style={s.row}>
        <Pressable disabled={busy} onPress={() => void like()}>
          <Text style={s.action}>
            {item.liked ? "♥" : "♡"} {item.like_count}
          </Text>
        </Pressable>
        <Pressable onPress={() => onReply(item.parent_id || item.id)}>
          <Text style={s.action}>Yanıtla</Text>
        </Pressable>
        {!item.parent_id && item.reply_count > 0 && (
          <Pressable
            disabled={busy}
            onPress={() =>
              open
                ? setOpen(false)
                : replies.length
                  ? setOpen(true)
                  : void more()
            }
          >
            <Text style={s.action}>
              {open ? "Yanıtları kapat" : `${item.reply_count} yanıtı aç`}
            </Text>
          </Pressable>
        )}
      </View>
      <Text style={s.error}>{error}</Text>
      {open && (
        <View style={s.replies}>
          {replies.map((c) => (
            <CommentThread
              key={c.id}
              token={token}
              item={c}
              postId={postId}
              onProfile={onProfile}
              onReply={onReply}
              onChange={(v, id) =>
                setReplies((old) =>
                  v
                    ? old.map((x) => (x.id === id ? v : x))
                    : old.filter((x) => x.id !== id),
                )
              }
            />
          ))}
          {next && (
            <Button
              title="Diğer yanıtlar"
              disabled={busy}
              onPress={() => void more()}
            />
          )}
        </View>
      )}
      {editing && sessionReady && (
        <Sheet
          title="Yorumu düzenle"
          onClose={() => {
            if (busy || commentEditLock.current) return;
            if (editText !== item.text) {
              Alert.alert("Değişiklikler kaydedilmedi", "Yorumdaki değişiklikleri silmek istiyor musunuz?", [
                { text: "Düzenlemeye devam et", style: "cancel" },
                { text: "Değişiklikleri sil", style: "destructive", onPress: () => setEditing(false) },
              ]);
            } else setEditing(false);
          }}
        >
          <View style={s.pad}>
            <TextInput
              accessibilityLabel="Yorumu düzenle"
              multiline
              maxLength={1500}
              value={editText}
              onChangeText={setEditText}
              editable={!busy}
              style={[s.input, { minHeight: 120 }]}
            />
            <Text style={s.error}>{error}</Text>
            <Button
              title={busy ? "Kaydediliyor…" : "Kaydet"}
              disabled={busy || !editText.trim()}
              onPress={async () => {
                if (commentEditLock.current || !editText.trim()) return;
                commentEditLock.current = true;
                setBusy(true);
                try {
                  const next = await api.patchComment(token, item, editText.trim());
                  onChange(next, item.id);
                  setEditing(false);
                  setError("");
                } catch (e) {
                  setError(message(e));
                } finally {
                  commentEditLock.current = false;
                  setBusy(false);
                }
              }}
            />
          </View>
        </Sheet>
      )}
    </View>
  );
}
function Comments({
  token,
  userId,
  post,
  onClose,
  onProfile,
}: {
  token: string;
  userId: number;
  post: api.SocialPost;
  onClose: () => void;
  onProfile: (id: number, name: string) => void;
}) {
  const [items, setItems] = useState<api.SocialComment[]>([]),
    [next, setNext] = useState<number | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [parent, setParent] = useState<number | undefined>(),
    lock = useRef(false),
    commentLoadGeneration = useRef(0),
    // Keep the exact pagination request that owns the lease. A first-page
    // refresh invalidates an older page request without letting its finally
    // block release a newer page request's lock.
    commentPageRequest = useRef<number | null>(null);
  const d = useDraft(userId, `comment.${post.id}`);
  const load = useCallback(
    async (after = 0) => {
      if (after && commentPageRequest.current !== null) return;
      const request = ++commentLoadGeneration.current;
      if (after) commentPageRequest.current = request;
      else commentPageRequest.current = null;
      setBusy(true);
      try {
        const page = await api.getComments(token, post.id, after);
        if (request !== commentLoadGeneration.current) return;
        setItems((v) =>
          after
            ? [...v, ...page.items.filter((x) => !v.some((y) => y.id === x.id))]
            : page.items,
        );
        // A non-advancing cursor would otherwise keep requesting the same page.
        setNext(
          page.next_cursor !== null &&
          Number.isSafeInteger(page.next_cursor) &&
          page.next_cursor > 0 &&
          (!after || page.next_cursor > after)
            ? page.next_cursor
            : null,
        );
        setError("");
      } catch (e) {
        if (request === commentLoadGeneration.current) setError(message(e));
      } finally {
        if (commentPageRequest.current === request) {
          commentPageRequest.current = null;
        }
        if (request === commentLoadGeneration.current) setBusy(false);
      }
    },
    [post.id, token],
  );
  useEffect(() => {
    commentPageRequest.current = null;
    void load();
    return () => {
      commentLoadGeneration.current++;
      commentPageRequest.current = null;
    };
  }, [load]);
  async function send() {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    try {
      await d.send((v) =>
        api.createComment(
          token,
          post.id,
          v.text,
          v.id,
          v.link ? Number(v.link) : undefined,
        ),
      );
      setParent(undefined);
      await load();
    } catch (e) {
      setError(message(e));
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  return (
    <Sheet
      title="Yorumlar"
      onClose={() => {
        if (!lock.current) onClose();
      }}
    >
      <FlatList
        data={items}
        keyExtractor={(x) => String(x.id)}
        contentContainerStyle={s.pad}
        refreshing={busy}
        onRefresh={() => void load()}
        renderItem={({ item }) => (
          <CommentThread
            token={token}
            item={item}
            postId={post.id}
            onProfile={onProfile}
            onReply={(id) => {
              if (!d.draft.attempted) {
                setParent(id);
                d.update({ link: String(id) });
              }
            }}
            onChange={(value, id) =>
              setItems((v) =>
                value
                  ? v.map((x) => (x.id === id ? value : x))
                  : v.filter((x) => x.id !== id),
              )
            }
          />
        )}
        ListEmptyComponent={
          <Text style={s.meta}>
            {busy ? "Yükleniyor…" : "Henüz yorum yok."}
          </Text>
        }
        ListFooterComponent={
          next ? (
            <Button
              title="Diğer yorumlar"
              disabled={busy}
              onPress={() => void load(next)}
            />
          ) : null
        }
      />
      <View style={s.composer}>
        {(parent || d.draft.link) && (
          <Pressable
            disabled={d.draft.attempted}
            onPress={() => {
              setParent(undefined);
              d.update({ link: "" });
            }}
          >
            <Text style={s.action}>
              Yanıt #{parent || d.draft.link} · İptal
            </Text>
          </Pressable>
        )}
        <Text style={s.error}>{error || d.error}</Text>
        <TextInput
          accessibilityLabel="Yorum yaz"
          multiline
          maxLength={1500}
          placeholder={post.comments_closed ? "Yorumlar kapalı" : "Yorum yaz…"}
          style={[s.input, { maxHeight: 100 }]}
          value={d.draft.text}
          editable={
            d.ready && !busy && !d.draft.attempted && !post.comments_closed
          }
          onChangeText={(text) => d.update({ text })}
        />
        <View style={s.row}>
          {["👍", "👏", "🦷", "😊"].map((emoji) => (
            <Pressable
              key={emoji}
              disabled={busy || d.draft.attempted}
              onPress={() =>
                d.update({ text: (d.draft.text + emoji).slice(0, 1500) })
              }
            >
              <Text style={{ fontSize: 24, padding: 5 }}>{emoji}</Text>
            </Pressable>
          ))}
        </View>
        <Button
          title={
            busy
              ? "Gönderiliyor…"
              : d.draft.attempted
                ? "Tekrar dene"
                : "Gönder"
          }
          disabled={
            !d.ready || busy || !d.draft.text.trim() || post.comments_closed
          }
          onPress={() => void send()}
        />
        {d.draft.attempted && (
          <Button
            title="Taslağı sil"
            disabled={busy}
            onPress={() => {
              void d.clear().catch((e) => setError(message(e)));
            }}
          />
        )}
      </View>
    </Sheet>
  );
}

function PostCard({
  token,
  userId,
  post,
  onUpdate,
  onComments,
  onProfile,
  onImage,
  onEdit,
  onFollow,
  onSupport,
  showExpertActions,
}: {
  token: string;
  userId: number;
  post: api.SocialPost;
  onUpdate: (p: api.SocialPost | null) => void;
  onComments: () => void;
  onProfile: () => void;
  onImage: (media: api.SocialPost["media"], index: number) => void;
  onEdit: () => void;
  onFollow: (authorId: number, followed: boolean) => Promise<boolean>;
  onSupport: () => void;
  showExpertActions: boolean;
}) {
  const [busy, setBusy] = useState(false),
    [followBusy, setFollowBusy] = useState(false),
    [moderationBusy, setModerationBusy] = useState(false),
    [error, setError] = useState(""),
    lock = useRef(false),
    followLock = useRef(false),
    moderationLock = useRef(false);
  const mutate = async (fn: () => Promise<api.SocialPost | null>) => {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    try {
      onUpdate(await fn());
      setError("");
    } catch (e) {
      setError(message(e));
    } finally {
      lock.current = false;
      setBusy(false);
    }
  };
  async function refreshModeration() {
    if (!post.owned || moderationLock.current || busy || followBusy) return;
    moderationLock.current = true;
    setModerationBusy(true);
    setError("");
    try {
      const latest = await api.getPostModerationStatus(token, post.id);
      onUpdate({
        ...post,
        status: latest.status,
        version: latest.version,
        moderation: latest.moderation,
      });
    } catch (e) {
      setError(message(e));
    } finally {
      moderationLock.current = false;
      setModerationBusy(false);
    }
  }

  async function sharePost() {
    if (post.status !== "PUBLISHED") return;
    try {
      const url = api.socialPostUrl(post.author_id, post.id);
      await Share.share({ message: url, url });
    } catch (e) {
      setError(message(e));
    }
  }
  async function toggleFollow() {
    if (followLock.current || busy) return;
    followLock.current = true;
    setFollowBusy(true);
    setError("");
    try {
      await onFollow(post.author_id, !post.author_followed);
    } catch (e) {
      setError(message(e));
    } finally {
      followLock.current = false;
      setFollowBusy(false);
    }
  }
  const [menuOpen, setMenuOpen] = useState(false);
  const menu = () => setMenuOpen(true);
  const choose = (action: () => void) => {
    setMenuOpen(false);
    action();
  };
  const coverMedia =
    post.link_url && post.cover_media_id
      ? post.media.find((item) => item.id === post.cover_media_id)
      : undefined;
  const gallery = post.media.filter(
    (item) => !(post.link_url && item.id === post.cover_media_id),
  );
  const createdAt = new Date(post.created_at);
  const createdAtLabel = Number.isNaN(createdAt.getTime())
    ? "Tarih bilinmiyor"
    : createdAt.toLocaleString("tr-TR", {
        day: "numeric",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
  return (
    <View style={s.card}>
      <View style={s.row}>
        <Pressable
          accessibilityLabel={`${post.author_name} profili`}
          onPress={onProfile}
          style={[s.row, { flex: 1 }]}
        >
          {post.author_photo ? (
            <Image
              source={api.socialImageSource(post.author_photo, token)}
              style={s.avatar}
            />
          ) : (
            <View style={[s.avatar, s.placeholder]}>
              <Text>{post.author_name[0]}</Text>
            </View>
          )}
          <View style={{ flex: 1 }}>
            <Text style={s.author}>{post.author_name}</Text>
            <Text style={s.verified}>✓ Mesleki belgesi doğrulanmış</Text>
            {!!post.author_specialty && (
              <Text style={s.meta}>{post.author_specialty}</Text>
            )}
            <Text style={s.meta}>{createdAtLabel}</Text>
          </View>
        </Pressable>
        {post.author_id !== userId &&
          typeof post.author_followed === "boolean" &&
          post.status === "PUBLISHED" && (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={post.author_followed ? "Takipten çık" : "Takip et"}
              accessibilityState={{ selected: post.author_followed }}
              disabled={busy || followBusy}
              onPress={() => void toggleFollow()}
              style={s.followButton}
            >
              <Text style={s.followButtonText}>
                {followBusy ? "…" : post.author_followed ? "Takip ediliyor" : "Takip et"}
              </Text>
            </Pressable>
          )}
        <Pressable
          accessibilityLabel="Gönderi işlemleri"
          disabled={busy || followBusy}
          onPress={menu}
        >
          <Text style={s.action}>•••</Text>
        </Pressable>
      </View>
      {post.pinned && <Text style={s.action}>📌 Sabit gönderi</Text>}
      <Text selectable style={s.body}>
        {post.text}
      </Text>
      {gallery.length > 0 && (
        <View style={s.gallery}>
          {gallery.map((item, index) => (
            <Pressable
              key={item.id}
              accessibilityRole="button"
              accessibilityLabel={`Gönderi görselini aç ${index + 1} / ${gallery.length}`}
              onPress={() => onImage(gallery, index)}
              style={s.galleryItem}
            >
              <Image
                source={api.socialImageSource(item.url, token)}
                style={s.galleryPhoto}
                resizeMode="cover"
              />
            </Pressable>
          ))}
        </View>
      )}
      {!!post.link_url && (
        <Pressable
          accessibilityRole="link"
          accessibilityLabel="Bağlantı önizlemesi"
          onPress={() => {
            if (/^https:\/\//i.test(post.link_url!))
              void Linking.openURL(post.link_url!).catch((e) =>
                setError(message(e)),
              );
          }}
          style={s.previewCard}
        >
          {coverMedia?.url && (
            <Image
              source={api.socialImageSource(coverMedia.url, token)}
              style={s.previewImage}
              resizeMode="cover"
            />
          )}
          <View style={{ flex: 1 }}>
            <Text style={s.previewTitle} numberOfLines={2}>
              {post.preview?.title ||
                post.preview?.site_name ||
                post.preview?.domain ||
                post.link_url}
            </Text>
            {!!post.preview?.domain && (
              <Text style={s.previewMeta}>{post.preview.domain}</Text>
            )}
            {!!post.preview?.description && (
              <Text style={s.previewDescription} numberOfLines={3}>
                {post.preview.description}
              </Text>
            )}
          </View>
        </Pressable>
      )}
      {post.status !== "PUBLISHED" && (
        <View style={s.moderationBox}>
          <Text style={s.moderationTitle}>
            {post.moderation?.wait_type === "OWNER_CHANGES"
              ? "Düzenleme gerekli"
              : post.status === "PENDING"
                ? post.moderation?.state === "FAILED"
                  ? post.moderation.retryable
                    ? "Otomatik kontrol yeniden denenecek"
                    : "Yönetici müdahalesi gerekiyor"
                  : "İnceleme bekliyor"
                : "Yayınlanmadı"}
          </Text>
          <Text style={s.meta}>
            {post.moderation?.reason ||
              (post.status === "PENDING"
                ? "Gönderi yayınlanmadan önce inceleniyor."
                : "Gönderi yayınlanmadı.")}
          </Text>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Yayın durumunu yenile"
            disabled={moderationBusy || busy || followBusy}
            onPress={() => void refreshModeration()}
            style={s.moderationAction}
          >
            <Text style={s.moderationActionText}>
              {moderationBusy ? "Kontrol ediliyor…" : "Durumu yenile"}
            </Text>
          </Pressable>
        </View>
      )}
      <View style={s.row}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={post.liked ? "Beğenmekten vazgeç" : "Beğen"}
          disabled={busy || post.status !== "PUBLISHED"}
          onPress={() =>
            void mutate(async () => ({
              ...post,
              ...(await api.setPostLike(token, post.id, !post.liked)),
            }))
          }
        >
          <Text style={s.action}>
            {post.liked ? "♥" : "♡"} {post.like_count}
          </Text>
        </Pressable>
        {!post.comments_closed ? (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={`Yorumlar ${post.comment_count}`}
            disabled={busy || post.status !== "PUBLISHED"}
            onPress={onComments}
          >
            <Text style={s.action}>Yorumlar · {post.comment_count}</Text>
          </Pressable>
        ) : (
          <Text style={s.meta}>Yorumlar kapalı</Text>
        )}
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Gönderi bağlantısını paylaş"
          disabled={busy || post.status !== "PUBLISHED"}
          onPress={() => void sharePost()}
        >
          <Text style={s.action}>Bağlantı</Text>
        </Pressable>
      </View>
      {showExpertActions && post.status === "PUBLISHED" && (
        <View style={s.row}>
          <Pressable accessibilityRole="button" onPress={onProfile}>
            <Text style={s.action}>Uzman profili</Text>
          </Pressable>
          {post.author_id !== userId &&
            post.author_support_available === true && (
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Uzmandan Destek Al"
                onPress={onSupport}
              >
                <Text style={s.action}>Uzmandan Destek Al</Text>
              </Pressable>
            )}
        </View>
      )}
      <Text style={s.error}>{error}</Text>
      {menuOpen && (
        <Sheet title="Gönderi işlemleri" onClose={() => setMenuOpen(false)}>
          <View style={s.pad}>
            {post.owned && showExpertActions ? (
              <Button
                title="Profilimde yönet"
                onPress={() => choose(onProfile)}
              />
            ) : post.owned ? (
              <>
                <Button title="Düzenle" onPress={() => choose(onEdit)} />
                <Button
                  title={post.pinned ? "Sabitlemeyi kaldır" : "Sabitle"}
                  onPress={() =>
                    choose(
                      () =>
                        void mutate(() =>
                          api.patchPost(token, post, { pinned: !post.pinned }),
                        ),
                    )
                  }
                />
                <Button
                  title={
                    post.comments_closed ? "Yorumları aç" : "Yorumları kapat"
                  }
                  onPress={() =>
                    choose(
                      () =>
                        void mutate(() =>
                          api.patchPost(token, post, {
                            comments_closed: !post.comments_closed,
                          }),
                        ),
                    )
                  }
                />
                <Button
                  title="Sil"
                  onPress={() =>
                    choose(() =>
                      Alert.alert("Gönderi silinsin mi?", "", [
                        { text: "Vazgeç" },
                        {
                          text: "Sil",
                          style: "destructive",
                          onPress: () =>
                            void mutate(async () => {
                              await api.deletePost(token, post.id);
                              return null;
                            }),
                        },
                      ]),
                    )
                  }
                />
              </>
            ) : (
              <Button
                title="Bildir"
                onPress={() =>
                  choose(() => {
                    api
                      .reportSocial(token, "POST", post.id)
                      .then(() => Alert.alert("Bildirim alındı"))
                      .catch((e) => setError(message(e)));
                  })
                }
              />
            )}
          </View>
        </Sheet>
      )}
    </View>
  );
}

export function DentalFlow({
  token,
  user,
  navigation,
  expertId,
  expertName,
  expertHeader,
  canCompose,
}: {
  token: string;
  user: User;
  navigation: any;
  expertId?: number;
  expertName?: string;
  expertHeader?: React.ReactNode;
  canCompose?: boolean;
}) {
  const [sessionEpoch, setSessionEpoch] = useState(0);
  const [readySession, setReadySession] = useState({ userId: user.id, token });
  const sessionKey = socialSessionKey(user.id, sessionEpoch);
  const sessionReady = isSocialSessionCurrent(readySession, { userId: user.id, token });
  const followLocks = useRef(new Set<string>());
  const feedFollowLocks = useRef(new Set<string>());
  const editLocks = useRef(new Set<string>());
  const profileGeneration = useRef(0);
  const [mode, setMode] = useState<"discover" | "following">("discover"),
    [selectedSpecialty, setSelectedSpecialty] = useState(""),
    [specialties, setSpecialties] = useState<string[]>([]),
    [compose, setCompose] = useState(false),
    [comments, setComments] = useState<api.SocialPost | null>(null),
    [image, setImage] = useState<{ media: api.SocialPost["media"]; index: number } | null>(null),
    [editing, setEditing] = useState<api.SocialPost | null>(null),
    [editText, setEditText] = useState(""),
    [saving, setSaving] = useState(false),
    [error, setError] = useState(""),
    [stats, setStats] = useState<Awaited<
      ReturnType<typeof api.getSocialStats>
    > | null>(null);
  const pages = usePagedRecords<api.SocialPost>(
    `${sessionKey}.${mode}.${expertId || 0}.${expertId ? "" : selectedSpecialty}`,
    async (before) => {
      if (expertId) {
        const p = await api.getExpertPosts(token, expertId, before);
        return { items: p.items, next_before: p.next_cursor };
      }
      const p = await api.getFeed(token, mode, before, selectedSpecialty);
      if (before === undefined) setSpecialties(p.specialties);
      return { items: p.items, next_before: p.next_cursor };
    },
    false,
    true,
  );
  const moderationRefreshLocks = useRef(new Set<string>());
  const moderationResumeGate = useRef(createModerationResumeGate());
  const sessionScope = useRef({ userId: user.id, token });
  sessionScope.current = { userId: user.id, token };
  const observedSession = useRef({ userId: user.id, token });
  useEffect(() => {
    // Advance only on a real identity change; do not duplicate the initial feed request.
    const nextSession = { userId: user.id, token };
    if (isSocialSessionCurrent(observedSession.current, nextSession)) return;
    observedSession.current = nextSession;
    setSessionEpoch((value) => value + 1);
  }, [user.id, token]);
  const refreshVisibleModeration = useCallback(async () => {
    if (moderationRefreshLocks.current.has(sessionKey)) return;
    const candidates = selectOwnedModerationCandidates(pages.items);
    if (!candidates.length) return;
    moderationRefreshLocks.current.add(sessionKey);
    const requestUserId = user.id;
    const requestToken = token;
    try {
      // At most five owned, unpublished cards are checked, two requests at a time.
      // No timer/polling is used; this runs only after an app or navigation resume.
      for (let offset = 0; offset < candidates.length; offset += 2) {
        const batch = candidates.slice(offset, offset + 2);
        await Promise.all(
          batch.map(async (candidate) => {
            try {
              const latest = await api.getPostModerationStatus(
                requestToken,
                candidate.id,
              );
              if (!isSocialSessionCurrent(sessionScope.current, { userId: requestUserId, token: requestToken })) {
                return;
              }
              pages.setItems((current) =>
                current.map((item) =>
                  item.id === candidate.id &&
                  item.owned &&
                  item.version <= latest.version
                    ? {
                        ...item,
                        status: latest.status,
                        version: latest.version,
                        moderation: latest.moderation,
                      }
                    : item,
                ),
              );
            } catch {
              // Resume refresh is best-effort. The visible manual retry remains available.
            }
          }),
        );
      }
    } finally {
      moderationRefreshLocks.current.delete(sessionKey);
    }
  }, [pages.items, pages.setItems, token, user.id]);
  const requestResumeModerationRefresh = useCallback(() => {
    if (moderationResumeGate.current()) {
      void refreshVisibleModeration();
    }
  }, [refreshVisibleModeration]);
  useEffect(() => {
    let previousState = AppState.currentState;
    let hasBlurred = false;
    const resumeIfFocused = () => {
      if (navigation?.isFocused?.() === false) return;
      requestResumeModerationRefresh();
    };
    const appStateSubscription = AppState.addEventListener(
      "change",
      (nextState) => {
        const resumed = isSocialAppResume(previousState, nextState);
        previousState = nextState;
        if (resumed) resumeIfFocused();
      },
    );
    const removeBlur = navigation?.addListener?.("blur", () => {
      hasBlurred = true;
    });
    const removeFocus = navigation?.addListener?.("focus", () => {
      if (!hasBlurred) return;
      hasBlurred = false;
      resumeIfFocused();
    });
    return () => {
      appStateSubscription.remove();
      if (typeof removeBlur === "function") removeBlur();
      if (typeof removeFocus === "function") removeFocus();
    };
  }, [navigation, requestResumeModerationRefresh]);
  const update = (
    p: api.SocialPost | null,
    id: number,
    expectedSession = { userId: user.id, token },
  ) => {
    if (!isSocialSessionCurrent(sessionScope.current, expectedSession)) return;
    pages.setItems((v) =>
      p ? v.map((x) => (x.id === id ? p : x)) : v.filter((x) => x.id !== id),
    );
  };
  const updateFollow = async (
    authorId: number,
    followed: boolean,
  ): Promise<boolean> => {
    const requestSession = { userId: user.id, token };
    const lockKey = `${sessionKey}:${authorId}`;
    if (feedFollowLocks.current.has(lockKey)) {
      throw new Error("Bu uzman için takip işlemi zaten sürüyor.");
    }
    feedFollowLocks.current.add(lockKey);
    try {
      const result = await api.setFollow(token, authorId, followed);
      if (!isSocialSessionCurrent(sessionScope.current, requestSession)) return false;
      const next = result.following_by_viewer;
      pages.setItems((v) =>
        mode === "following" && !next
          ? v.filter((x) => x.author_id !== authorId)
          : v.map((x) =>
              x.author_id === authorId ? { ...x, author_followed: next } : x,
            ),
      );
      return next;
    } finally {
      feedFollowLocks.current.delete(lockKey);
    }
  };
  useEffect(() => {
    // Hide and discard account-owned overlays before the new session can paint.
    moderationResumeGate.current = createModerationResumeGate();
    setReadySession({ userId: user.id, token });
    setCompose(false);
    setComments(null);
    setImage(null);
    setEditing(null);
    setEditText("");
    setSaving(false);
    setError("");
    setStats(null);
    setSpecialties([]);
  }, [sessionKey]);
  useEffect(() => {
    const request = ++profileGeneration.current;
    setStats(null);
    setError("");
    if (expertId)
      api
        .getSocialStats(token, expertId)
        .then((result) => { if (request === profileGeneration.current) setStats(result); })
        .catch((e) => { if (request === profileGeneration.current) setError(message(e)); });
    return () => { profileGeneration.current++; };
  }, [token, user.id, expertId]);
  const profile = (id: number, name: string) => {
    if (!isSocialSessionCurrent(sessionScope.current, { userId: user.id, token })) return;
    setComments(null);
    navigation.push("ExpertProfile", { id, name });
  };
  const header = expertHeader ? <View>{expertHeader}{expertId===user.id&&canCompose&&<Button title="Gönderi Paylaş" onPress={()=>setCompose(true)}/>}<Text style={s.error}>{error||pages.error}</Text>{pages.error&&<Button title="Tekrar dene" onPress={pages.refresh}/>}</View> : (
    <View>
      <View style={s.header}>
        <Text style={s.title}>{expertName || "Dental Akış"}</Text>
        {expertId === user.id && canCompose && (
          <Pressable accessibilityRole="button" accessibilityLabel="Gönderi paylaş" onPress={() => setCompose(true)}>
            <Text style={s.action}>＋ Paylaş</Text>
          </Pressable>
        )}
      </View>
      {!expertId && (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Uzmanları keşfet"
          onPress={() => navigation.navigate("ExpertDirectory")}
          style={{ alignSelf: "flex-end", marginBottom: 8 }}
        >
          <Text style={s.action}>Uzmanları keşfet ↗</Text>
        </Pressable>
      )}
      {expertId ? (
        <View style={s.card}>
          <Text style={s.meta}>
            {stats
              ? `${stats.followers} takipçi · ${stats.posts} gönderi · ${stats.publications} yayın`
              : "Profil yükleniyor…"}
          </Text>
          {stats && expertId !== user.id && (
            <Button
              title={stats.following_by_viewer ? "Takibi bırak" : "Takip et"}
              disabled={saving}
              onPress={async () => {
                const requestSession = { userId: user.id, token };
                if (followLocks.current.has(sessionKey)) return;
                const request = profileGeneration.current;
                followLocks.current.add(sessionKey);
                setSaving(true);
                try {
                  const r = await api.setFollow(
                    token,
                    expertId,
                    !stats.following_by_viewer,
                  );
                  if (request !== profileGeneration.current || !isSocialSessionCurrent(sessionScope.current, requestSession)) return;
                  // The follow write succeeded; retain its authoritative state even if refreshing counts fails.
                  setStats((previous) => previous ? {
                    ...previous,
                    following_by_viewer: r.following_by_viewer,
                  } : previous);
                  try {
                    const latest = await api.getSocialStats(token, expertId);
                    if (request === profileGeneration.current)
                      setStats({ ...latest, following_by_viewer: r.following_by_viewer });
                  } catch (refreshError) {
                    if (request === profileGeneration.current)
                      setError("Takip güncellendi; güncel sayaç alınamadı: " + message(refreshError));
                  }
                } catch (e) {
                  if (request === profileGeneration.current) setError(message(e));
                } finally {
                  followLocks.current.delete(sessionKey);
                  if (isSocialSessionCurrent(sessionScope.current, requestSession)) setSaving(false);
                }
              }}
            />
          )}
          {expertId !== user.id && (
            <Button
              title="Uzmandan destek al"
              onPress={() =>
                navigation.navigate("NewConsultation", {
                  expert: {
                    user_id: expertId,
                    display_name: expertName || "Uzman",
                  },
                })
              }
            />
          )}
        </View>
      ) : (
        <View style={s.row}>
          {(["discover", "following"] as const).map((m) => (
            <Pressable
              key={m}
              onPress={() => setMode(m)}
              style={[s.tab, mode === m && { backgroundColor: C.navy }]}
            >
              <Text style={{ color: mode === m ? "white" : C.navy }}>
                {m === "discover" ? "Keşfet" : "Takip Ettiklerim"}
              </Text>
            </Pressable>
          ))}
        </View>
      )}
      {!expertId && specialties.length > 0 && (
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={s.filterRow}
          accessibilityLabel="Branşa göre filtrele"
        >
          {["", ...specialties].map((specialty) => {
            const selected = selectedSpecialty === specialty;
            return (
              <Pressable
                key={specialty || "all"}
                accessibilityRole="button"
                accessibilityLabel={`Branş filtresi: ${specialty || "Tümü"}`}
                accessibilityState={{ selected }}
                onPress={() => setSelectedSpecialty(specialty)}
                style={[s.filterChip, selected && s.filterChipSelected]}
              >
                <Text
                  style={[
                    s.filterChipText,
                    selected && s.filterChipTextSelected,
                  ]}
                >
                  {specialty || "Tümü"}
                </Text>
              </Pressable>
            );
          })}
        </ScrollView>
      )}
      <Text style={s.error}>{error || pages.error}</Text>
      {pages.error && <Button title="Tekrar dene" onPress={pages.refresh} />}
    </View>
  );
  return (
    <View style={s.page}>
      <FlatList
        key={sessionKey}
        data={sessionReady ? pages.items : []}
        keyExtractor={(p) => String(p.id)}
        contentContainerStyle={s.pad}
        initialNumToRender={5}
        maxToRenderPerBatch={5}
        windowSize={7}
        refreshing={sessionReady && pages.busy}
        onRefresh={sessionReady ? pages.refresh : undefined}
        ListHeaderComponent={sessionReady ? header : null}
        renderItem={({ item }) => (
          <PostCard
            token={token}
            userId={user.id}
            post={item}
            onFollow={updateFollow}
            showExpertActions={!expertId}
            onSupport={() => {
              if (!isSocialSessionCurrent(sessionScope.current, { userId: user.id, token })) return;
              navigation.navigate("NewConsultation", {
                expert: {
                  user_id: item.author_id,
                  display_name: item.author_name,
                },
              });
            }}
            onUpdate={(p) => update(p, item.id, { userId: user.id, token })}
            onComments={() => { if (isSocialSessionCurrent(sessionScope.current, { userId: user.id, token })) setComments(item); }}
            onProfile={() => profile(item.author_id, item.author_name)}
            onImage={(media, index) => { if (isSocialSessionCurrent(sessionScope.current, { userId: user.id, token })) setImage({ media, index }); }}
            onEdit={() => {
              if (!isSocialSessionCurrent(sessionScope.current, { userId: user.id, token })) return;
              setEditing(item);
              setEditText(item.text);
              setError("");
            }}
          />
        )}
        ListEmptyComponent={
          !sessionReady ? <ActivityIndicator color={C.navy} /> : (
            <Text style={s.meta}>
              {pages.busy ? "Yükleniyor…" : "Henüz gönderi yok."}
            </Text>
          )
        }
        ListFooterComponent={
          sessionReady && pages.hasMore ? (
            <Button
              title="Daha fazla gönderi"
              disabled={pages.busy}
              onPress={pages.loadMore}
            />
          ) : null
        }
      />
      {compose && sessionReady && (
        <Composer
          key={`${user.id}:${token}`}
          token={token}
          userId={user.id}
          onClose={() => { if (isSocialSessionCurrent(sessionScope.current, { userId: user.id, token })) setCompose(false); }}
          onPosted={(p) => {
            if (!isSocialSessionCurrent(sessionScope.current, { userId: user.id, token })) return;
            pages.setItems((v) => [p, ...v.filter((x) => x.id !== p.id)]);
            setError("");
          }}
        />
      )}
      {comments && sessionReady && (
        <Comments
          key={`${sessionKey}:${comments.id}`}
          token={token}
          userId={user.id}
          post={comments}
          onClose={() => {
            if (!isSocialSessionCurrent(sessionScope.current, { userId: user.id, token })) return;
            setComments(null);
            void pages.refresh();
          }}
          onProfile={profile}
        />
      )}
      {image && sessionReady && (
        <NativeSocialMediaViewer
          key={`${sessionKey}:media:${image.media.map((item) => item.id).join(",")}`}
          visible={!!image}
          token={token}
          media={image.media}
          initialIndex={image.index}
          onClose={() => { if (isSocialSessionCurrent(sessionScope.current, { userId: user.id, token })) setImage(null); }}
        />
      )}
      {editing && sessionReady && (
        <Sheet
          title="Gönderiyi düzenle"
          onClose={() => {
            if (saving || editLocks.current.has(sessionKey)) return;
            if (editText !== editing.text) {
              Alert.alert(
                "Değişiklikler kaydedilmedi",
                "Gönderi düzenlemesindeki değişiklikleri silmek istiyor musunuz?",
                [
                  { text: "Düzenlemeye devam et", style: "cancel" },
                  { text: "Değişiklikleri sil", style: "destructive", onPress: () => setEditing(null) },
                ],
              );
            } else {
              setEditing(null);
            }
          }}
        >
          <View style={s.pad}>
            <TextInput
              style={[s.input, { minHeight: 150 }]}
              multiline
              maxLength={5000}
              value={editText}
              onChangeText={setEditText}
              editable={!saving}
            />
            <Text style={s.error}>{error}</Text>
            <Button
              title={saving ? "Kaydediliyor…" : "Kaydet"}
              disabled={saving}
              onPress={async () => {
                const requestSession = { userId: user.id, token };
                if (editLocks.current.has(sessionKey) || !editText.trim()) return;
                editLocks.current.add(sessionKey);
                setSaving(true);
                try {
                  const p = await api.patchPost(token, editing, {
                    text: editText.trim(),
                  });
                  if (!isSocialSessionCurrent(sessionScope.current, requestSession)) return;
                  update(p, p.id, requestSession);
                  setEditing(null);
                  setError("");
                } catch (e) {
                  if (isSocialSessionCurrent(sessionScope.current, requestSession)) setError(message(e));
                } finally {
                  editLocks.current.delete(sessionKey);
                  if (isSocialSessionCurrent(sessionScope.current, requestSession)) setSaving(false);
                }
              }}
            />
          </View>
        </Sheet>
      )}
    </View>
  );
}
const s = StyleSheet.create({
  page: { flex: 1, backgroundColor: C.bg },
  pad: { padding: 16, paddingBottom: 28 },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    padding: 12,
    gap: 8,
  },
  title: { fontSize: 23, fontWeight: "800", color: C.navy, flex: 1 },
  card: {
    padding: 14,
    backgroundColor: "white",
    borderRadius: 16,
    borderWidth: 1,
    borderColor: C.line,
    marginBottom: 12,
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: 16,
    flexWrap: "wrap",
  },
  author: { fontSize: 14, fontWeight: "800", color: C.text },
  verified: { fontSize: 11, fontWeight: "700", color: "#1769AA", marginTop: 2 },
  moderationBox: { padding: 12, borderRadius: 12, borderWidth: 1, borderColor: "#F0D9A8", backgroundColor: "#FFF9ED", marginVertical: 8, gap: 6 },
  moderationTitle: { color: "#8A4B08", fontSize: 13, fontWeight: "800" },
  moderationAction: { alignSelf: "flex-start", minHeight: 40, justifyContent: "center", paddingHorizontal: 10, borderRadius: 9, backgroundColor: "#FCECCB" },
  moderationActionText: { color: "#75400B", fontSize: 12, fontWeight: "800" },
  body: { fontSize: 15, color: C.text, lineHeight: 23, marginVertical: 10 },
  meta: { fontSize: 12, color: C.muted, lineHeight: 18 },
  action: {
    fontSize: 14,
    color: C.navy,
    fontWeight: "700",
    paddingVertical: 10,
  },
  avatar: { width: 40, height: 40, borderRadius: 20 },
  placeholder: {
    backgroundColor: C.line,
    alignItems: "center",
    justifyContent: "center",
  },
  photo: {
    width: "100%",
    height: 250,
    backgroundColor: C.bg,
    borderRadius: 10,
    marginVertical: 6,
  },
  gallery: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginVertical: 8 },
  galleryItem: { width: "48%", minWidth: "46%", flexGrow: 1 },
  galleryPhoto: { width: "100%", height: 150, borderRadius: 10, backgroundColor: C.bg },
  mediaGrid: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginVertical: 10 },
  mediaItem: { width: "48%", flexGrow: 1, borderRadius: 12, overflow: "hidden", backgroundColor: C.bg },
  mediaImage: { width: "100%", height: 132, backgroundColor: C.bg },
  mediaControls: { flexDirection: "row", alignItems: "center", justifyContent: "space-around", padding: 5, backgroundColor: "#EEF3F8" },
  mediaControl: { minWidth: 42, minHeight: 36, alignItems: "center", justifyContent: "center", borderRadius: 10, backgroundColor: "white" },
  mediaControlText: { color: C.navy, fontSize: 21, fontWeight: "800" },
  coverControl: { paddingVertical: 8, paddingHorizontal: 10, alignItems: "center", backgroundColor: "#EEF3F8" },
  coverControlSelected: { backgroundColor: "#DCEAF5" },
  coverControlText: { color: C.navy, fontSize: 11, fontWeight: "700" },
  coverControlTextSelected: { color: "#075B75" },
  previewCard: { flexDirection: "row", gap: 12, alignItems: "center", padding: 10, borderWidth: 1, borderColor: C.line, borderRadius: 14, backgroundColor: "white", marginVertical: 8 },
  previewImage: { width: 88, height: 88, borderRadius: 10, backgroundColor: C.bg },
  previewTitle: { color: C.navy, fontSize: 14, fontWeight: "800", lineHeight: 19 },
  previewMeta: { color: C.muted, fontSize: 11, marginTop: 3 },
  previewDescription: { color: C.muted, fontSize: 12, lineHeight: 17, marginTop: 4 },
  button: {
    backgroundColor: C.navy,
    padding: 14,
    borderRadius: 12,
    alignItems: "center",
    marginTop: 8,
  },
  buttonText: { color: "white", fontWeight: "700" },
  tab: {
    padding: 12,
    borderRadius: 16,
    backgroundColor: "white",
    marginBottom: 14,
  },
  filterRow: { paddingHorizontal: 4, paddingBottom: 10 },
  filterChip: {
    paddingHorizontal: 14,
    paddingVertical: 9,
    borderRadius: 18,
    borderWidth: 1,
    borderColor: C.line,
    backgroundColor: "white",
    marginRight: 8,
  },
  filterChipSelected: { backgroundColor: C.navy, borderColor: C.navy },
  filterChipText: { fontSize: 12, fontWeight: "700", color: C.navy },
  filterChipTextSelected: { color: "white" },
  followButton: {
    borderWidth: 1,
    borderColor: C.line,
    borderRadius: 16,
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  followButtonText: { color: C.navy, fontSize: 12, fontWeight: "800" },
  input: {
    padding: 12,
    borderWidth: 1,
    borderColor: C.line,
    borderRadius: 12,
    marginVertical: 8,
    color: C.text,
    backgroundColor: "white",
    textAlignVertical: "top",
  },
  error: { color: "#B42318", fontSize: 13 },
  composer: {
    padding: 12,
    borderTopWidth: 1,
    borderColor: C.line,
    backgroundColor: "white",
  },
  comment: { borderBottomWidth: 1, borderColor: C.line, paddingVertical: 12 },
  replies: { paddingLeft: 16, borderLeftWidth: 2, borderColor: C.line },
});
