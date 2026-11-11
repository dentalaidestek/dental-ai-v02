import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  FlatList,
  Image,
  KeyboardAvoidingView,
  Linking,
  Modal,
  Platform,
  Pressable,
  ScrollView,
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
  }, [key]);
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
  return { draft, ready, error, update, clear, send };
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
    [error, setError] = useState(""),
    [localPhoto, setLocalPhoto] = useState<string | null>(null),
    lock = useRef(false);
  async function image() {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    try {
      const p = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!p.granted) throw Error("Fotoğraf izni verilmedi.");
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ["images"],
        quality: 0.8,
        allowsMultipleSelection: false,
      });
      if (result.canceled) return;
      const a = result.assets[0];
      const uploaded = await api.uploadSocialImage(token, {
        uri: a.uri,
        name: a.fileName || "social.jpg",
        type: a.mimeType || "image/jpeg",
      });
      d.update({ media_ids: [...d.draft.media_ids, uploaded.id] });
      setLocalPhoto(a.uri);
    } catch (e) {
      setError(message(e));
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  async function post() {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    try {
      const p = await d.send((v) =>
        api.createPost(token, {
          text: v.text,
          media_ids: v.media_ids,
          idempotency_key: v.id,
          ...(v.link.trim() ? { link_url: v.link.trim() } : {}),
        }),
      );
      onPosted(p);
      onClose();
    } catch (e) {
      setError(message(e));
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  return (
    <Sheet
      title="Gönderi paylaş"
      onClose={() => {
        if (!lock.current) onClose();
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
              <Button
                title="Bozuk taslağı temizle"
                onPress={() => {
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
              onChangeText={(link) => d.update({ link })}
              style={s.input}
            />
            <Text style={s.meta}>{d.draft.media_ids.length}/4 fotoğraf</Text>
            {localPhoto && <Image accessibilityLabel="Yüklenen son fotoğrafın önizlemesi" source={{uri:localPhoto}} resizeMode="contain" style={{width:"100%",height:220,borderRadius:12,backgroundColor:C.bg,marginVertical:8}}/>}
            {!!d.draft.media_ids.length && <Text style={s.meta}>Fotoğraf taslağa eklendi. Paylaşmadan önce metni ve fotoğrafları kontrol edin.</Text>}
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
      {editing && (
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
    commentPageLock = useRef(false);
  const d = useDraft(userId, `comment.${post.id}`);
  const load = useCallback(
    async (after = 0) => {
      if (after && commentPageLock.current) return;
      const request = ++commentLoadGeneration.current;
      if (after) commentPageLock.current = true;
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
        if (after) commentPageLock.current = false;
        if (request === commentLoadGeneration.current) setBusy(false);
      }
    },
    [post.id, token],
  );
  useEffect(() => {
    void load();
    return () => { commentLoadGeneration.current++; };
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
  post,
  onUpdate,
  onComments,
  onProfile,
  onImage,
  onEdit,
}: {
  token: string;
  post: api.SocialPost;
  onUpdate: (p: api.SocialPost | null) => void;
  onComments: () => void;
  onProfile: () => void;
  onImage: (url: string) => void;
  onEdit: () => void;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    lock = useRef(false);
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
  const [menuOpen, setMenuOpen] = useState(false);
  const menu = () => setMenuOpen(true);
  const choose = (action: () => void) => {
    setMenuOpen(false);
    action();
  };
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
            <Text style={s.meta}>
              {post.author_specialty ||
                new Date(post.created_at).toLocaleDateString("tr-TR")}
            </Text>
          </View>
        </Pressable>
        <Pressable
          accessibilityLabel="Gönderi işlemleri"
          disabled={busy}
          onPress={menu}
        >
          <Text style={s.action}>•••</Text>
        </Pressable>
      </View>
      {post.pinned && <Text style={s.action}>📌 Sabit gönderi</Text>}
      <Text selectable style={s.body}>
        {post.text}
      </Text>
      {post.media.map((m) => (
        <Pressable key={m.id} onPress={() => onImage(m.url)}>
          <Image
            source={api.socialImageSource(m.url, token)}
            style={s.photo}
            resizeMode="contain"
          />
        </Pressable>
      ))}
      {!!post.link_url && (
        <Pressable
          onPress={() => {
            if (/^https?:\/\//i.test(post.link_url!))
              void Linking.openURL(post.link_url!).catch((e) =>
                setError(message(e)),
              );
          }}
        >
          <Text style={s.action} numberOfLines={2}>
            {post.link_url}
          </Text>
        </Pressable>
      )}
      {post.status !== "PUBLISHED" && (
        <Text style={s.meta}>İnceleme durumu: {post.status}</Text>
      )}
      <View style={s.row}>
        <Pressable
          accessibilityRole="button"
          disabled={busy}
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
        <Pressable onPress={onComments}>
          <Text style={s.action}>Yorumlar · {post.comment_count}</Text>
        </Pressable>
      </View>
      <Text style={s.error}>{error}</Text>
      {menuOpen && (
        <Sheet title="Gönderi işlemleri" onClose={() => setMenuOpen(false)}>
          <View style={s.pad}>
            {post.owned ? (
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
}: {
  token: string;
  user: User;
  navigation: any;
  expertId?: number;
  expertName?: string;
}) {
  const followLock = useRef(false);
  const editLock = useRef(false);
  const profileGeneration = useRef(0);
  const [mode, setMode] = useState<"discover" | "following">("discover"),
    [compose, setCompose] = useState(false),
    [comments, setComments] = useState<api.SocialPost | null>(null),
    [image, setImage] = useState<string | null>(null),
    [editing, setEditing] = useState<api.SocialPost | null>(null),
    [editText, setEditText] = useState(""),
    [saving, setSaving] = useState(false),
    [error, setError] = useState(""),
    [stats, setStats] = useState<Awaited<
      ReturnType<typeof api.getSocialStats>
    > | null>(null);
  const pages = usePagedRecords<api.SocialPost>(
    `${user.id}.${mode}.${expertId || 0}`,
    async (before) => {
      const p = expertId
        ? await api.getExpertPosts(token, expertId, before)
        : await api.getFeed(token, mode, before);
      return { items: p.items, next_before: p.next_cursor };
    },
    false,
    true,
  );
  const update = (p: api.SocialPost | null, id: number) =>
    pages.setItems((v) =>
      p ? v.map((x) => (x.id === id ? p : x)) : v.filter((x) => x.id !== id),
    );
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
  }, [token, expertId]);
  const profile = (id: number, name: string) => {
    setComments(null);
    navigation.push("ExpertProfile", { id, name });
  };
  const header = (
    <View>
      <View style={s.header}>
        <Text style={s.title}>{expertName || "Dental Akış"}</Text>
        {(!expertId || expertId === user.id) && (
          <Pressable accessibilityRole="button" accessibilityLabel="Gönderi paylaş" onPress={() => setCompose(true)}>
            <Text style={s.action}>＋ Paylaş</Text>
          </Pressable>
        )}
      </View>
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
                if (followLock.current) return;
                const request = profileGeneration.current;
                followLock.current = true;
                setSaving(true);
                try {
                  const r = await api.setFollow(
                    token,
                    expertId,
                    !stats.following_by_viewer,
                  );
                  if (request !== profileGeneration.current) return;
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
                  followLock.current = false;
                  setSaving(false);
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
                {m === "discover" ? "Keşfet" : "Takip edilenler"}
              </Text>
            </Pressable>
          ))}
        </View>
      )}
      <Text style={s.error}>{error || pages.error}</Text>
      {pages.error && <Button title="Tekrar dene" onPress={pages.refresh} />}
    </View>
  );
  return (
    <View style={s.page}>
      <FlatList
        data={pages.items}
        keyExtractor={(p) => String(p.id)}
        contentContainerStyle={s.pad}
        initialNumToRender={5}
        maxToRenderPerBatch={5}
        windowSize={7}
        refreshing={pages.busy}
        onRefresh={pages.refresh}
        ListHeaderComponent={header}
        renderItem={({ item }) => (
          <PostCard
            token={token}
            post={item}
            onUpdate={(p) => update(p, item.id)}
            onComments={() => setComments(item)}
            onProfile={() => profile(item.author_id, item.author_name)}
            onImage={setImage}
            onEdit={() => {
              setEditing(item);
              setEditText(item.text);
              setError("");
            }}
          />
        )}
        ListEmptyComponent={
          <Text style={s.meta}>
            {pages.busy ? "Yükleniyor…" : "Henüz gönderi yok."}
          </Text>
        }
        ListFooterComponent={
          pages.hasMore ? (
            <Button
              title="Daha fazla gönderi"
              disabled={pages.busy}
              onPress={pages.loadMore}
            />
          ) : null
        }
      />
      {compose && (
        <Composer
          token={token}
          userId={user.id}
          onClose={() => setCompose(false)}
          onPosted={(p) => {
            pages.setItems((v) => [p, ...v.filter((x) => x.id !== p.id)]);
            setError("");
          }}
        />
      )}
      {comments && (
        <Comments
          key={comments.id}
          token={token}
          userId={user.id}
          post={comments}
          onClose={() => {
            setComments(null);
            void pages.refresh();
          }}
          onProfile={profile}
        />
      )}
      {image && (
        <Sheet title="Fotoğraf" onClose={() => setImage(null)}>
          <Image
            source={api.socialImageSource(image, token)}
            style={{ flex: 1 }}
            resizeMode="contain"
          />
        </Sheet>
      )}
      {editing && (
        <Sheet
          title="Gönderiyi düzenle"
          onClose={() => {
            if (saving || editLock.current) return;
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
                if (editLock.current || !editText.trim()) return;
                editLock.current = true;
                setSaving(true);
                try {
                  const p = await api.patchPost(token, editing, {
                    text: editText.trim(),
                  });
                  update(p, p.id);
                  setEditing(null);
                  setError("");
                } catch (e) {
                  setError(message(e));
                } finally {
                  editLock.current = false;
                  setSaving(false);
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
