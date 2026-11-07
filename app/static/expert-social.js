/* Scoped enhancement of the existing expert profile; all untrusted text uses DOM text nodes. */
(() => {
  "use strict";
  if (window.DentalSocial) {
    window.DentalSocial.mountAll();
    return;
  }
  const API = "/api/expert-social";
  const labels = {
    PUBLISHED: "Yayınlandı",
    PENDING: "İncelemede",
    REJECTED: "Reddedildi",
  };
  const sourceLabels = {
    ORCID: "ORCID kaydı",
    DOI_MATCH: "DOI ile eşleşen kayıt",
    MANUAL: "Manuel ekleme",
  };
  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }
  function button(text, cls, fn) {
    const n = el("button", cls, text);
    n.type = "button";
    n.addEventListener("click", fn);
    return n;
  }
  async function api(path, method = "GET", data) {
    const controller = new AbortController(),
      timer = setTimeout(() => controller.abort(), 25000);
    try {
      const response = await fetch(API + path, {
        method,
        credentials: "same-origin",
        cache: "no-store",
        headers: {
          "X-Dental-Social": "1",
          ...(data !== undefined ? { "Content-Type": "application/json" } : {}),
        },
        ...(data !== undefined ? { body: JSON.stringify(data) } : {}),
        signal: controller.signal,
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) {
        let message = result.detail;
        if (Array.isArray(message))
          message = "Alanları ve karakter sınırlarını kontrol edin.";
        throw new Error(
          typeof message === "string"
            ? message
            : "İşlem tamamlanamadı. Yeniden deneyin.",
        );
      }
      return result;
    } catch (error) {
      if (error.name === "AbortError")
        throw new Error(
          "Bağlantı yavaş. Taslağınız korundu; yeniden deneyebilirsiniz.",
        );
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }
  function href(raw) {
    try {
      const u = new URL(raw);
      return u.protocol === "https:" ? u.href : null;
    } catch {
      return null;
    }
  }
  function external(raw, text, cls) {
    const a = el("a", cls, text);
    const url = href(raw);
    if (url) a.href = url;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    return a;
  }
  function linkedText(raw) {
    const out = el("p", "ds-post-text");
    let last = 0;
    for (const m of raw.matchAll(/https:\/\/[^\s<>]+/g)) {
      out.append(document.createTextNode(raw.slice(last, m.index)));
      const url = m[0].replace(/[.,;!?)]+$/, "");
      out.append(external(url, url));
      out.append(document.createTextNode(m[0].slice(url.length)));
      last = m.index + m[0].length;
    }
    out.append(document.createTextNode(raw.slice(last)));
    return out;
  }
  function statusBadge(status) {
    return el(
      "span",
      "ds-status" + (status === "REJECTED" ? " is-rejected" : ""),
      labels[status] || status,
    );
  }
  function linkCard(url, preview, cover) {
    const a = external(url, undefined, "ds-link-card");
    if (cover) {
      const img = el("img");
      img.src = cover;
      img.alt = "Bağlantı kapağı";
      img.loading = "lazy";
      a.append(img);
    }
    const body = el("div");
    let domain = "Bağlantı";
    try {
      domain = new URL(url).hostname;
    } catch {}
    body.append(
      el(
        "small",
        "",
        preview?.site_name ? preview.site_name + " · " + domain : domain,
      ),
      el("strong", "", preview?.title || domain),
    );
    if (preview?.description) body.append(el("p", "", preview.description));
    a.append(body);
    return a;
  }
  function date(raw) {
    const d = new Date(raw);
    return Number.isNaN(d.valueOf())
      ? ""
      : d.toLocaleString("tr-TR", {
          day: "numeric",
          month: "short",
          year: "numeric",
          hour: "2-digit",
          minute: "2-digit",
        });
  }
  const iconPaths = {
    heart:
      "M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z",
    comment:
      "M21 11.5a8.5 8.5 0 0 1-8.5 8.5H4l-3 2 1.5-6A8.5 8.5 0 1 1 21 11.5Z",
    share: "M9 12h12m-4-4 4 4-4 4M13 5H4v14h9",
  };
  function actionIcon(b,name){const icons={heart:'heart',comment:'chat-circle-text',share:'share-network'};const img=el('img','ds-action-icon');img.src='/static/expert-icons/'+icons[name]+'.svg';img.alt='';b.prepend(img);}
  async function copyLink(value) {
    if (navigator.clipboard?.writeText)
      return navigator.clipboard.writeText(value);
    const input = el("textarea");
    input.value = value;
    input.style.position = "fixed";
    input.style.opacity = "0";
    document.body.append(input);
    input.select();
    const ok = document.execCommand("copy");
    input.remove();
    if (!ok)
      throw new Error(
        "Bağlantı kopyalanamadı. Tarayıcı adresini paylaşabilirsiniz.",
      );
  }
  function uuid() {
    return crypto.randomUUID
      ? crypto.randomUUID()
      : `${1e7}-${1e3}-${4e3}-${8e3}-${1e11}`.replace(/[018]/g, (c) =>
          (
            c ^
            (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (c / 4)))
          ).toString(16),
        );
  }

  function mount(root) {
    if (root.dataset.mounted) return;
    root.dataset.mounted = "1";
    const $ = (q) => root.querySelector(q),
      owner = root.dataset.owner === "1",
      expertId = Number(root.dataset.expertId),
      userId = Number(root.dataset.userId);
    const management=root.dataset.management==="1";
    const notice = $("[data-notice]");
    function say(message) {
      notice.hidden = false;
      notice.textContent = message;
    }
    const feed = $("[data-feed]"),
      pubList = $("[data-publications]");
    let postCursor = null,
      pubCursor = null,
      pubsLoaded = false,
      postsLoading = false,
      pubsLoading = false;
    const posts = new Map(),
      publications = new Map();
    const draftKey = `dai-social-v1:${userId}:${expertId}`;
    let saved = {};
    try {
      saved = JSON.parse(sessionStorage.getItem(draftKey) || "{}");
    } catch {}
    let draft = {
        text: saved.text || "",
        media: saved.media || [],
        linkUrl: saved.linkUrl || null,
        preview: saved.preview || null,
        key: saved.key || uuid(),
      },
      editing = null,
      uploading = 0,
      sending = false,
      previewSequence = 0,
      previewTimer = null,
      removedUrl = null;
    const dialog = $("[data-composer]"),
      text = $("[data-post-text]");
    if(management && dialog)$('[data-panel="posts"]').prepend(dialog);
    function saveDraft() {
      if (editing) return;
      try {
        sessionStorage.setItem(
          draftKey,
          JSON.stringify({ ...draft, media: draft.media.filter((m) => m.id) }),
        );
      } catch {
        say(
          "Tarayıcı taslak saklamayı kapatmış. Bu sayfayı kapatmadan paylaşın.",
        );
      }
    }
    function resetDraft() {
      draft = {
        text: "",
        media: [],
        linkUrl: null,
        preview: null,
        key: uuid(),
      };
      saveDraft();
    }
    function checkDraft() {
      const uploadError = draft.media.some((m) => !m.id);
      if (uploadError)
        throw new Error("Yüklenemeyen görseli yeniden yükleyin veya kaldırın.");
    }
    function openDialog(d) {
      if (!d) return;
      if (management && d===dialog) {d.scrollIntoView({block:'nearest'});return;}
      if (d.open) return;
      d.showModal();
      history.pushState({ ...history.state, dsDialog: true }, "");
      adjustViewport();
    }
    function closeDialog(d, fromHistory = false) {
      if (management && d===dialog) {resetInlineComposer();return;}
      if (!d?.open) return;
      d.close();
      document.body.style.overflow = "";
      if (!fromHistory && history.state?.dsDialog) history.back();
    }
    root.querySelectorAll("dialog").forEach((d) => {
      d.addEventListener("cancel", (e) => {
        e.preventDefault();
        closeDialog(d);
      });
      d.querySelectorAll("[data-close]").forEach((b) =>
        b.addEventListener("click", () => closeDialog(d)),
      );
    });
    window.addEventListener("popstate", () => {
      root
        .querySelectorAll("dialog[open]")
        .forEach((d) => closeDialog(d, true));
    });
    function adjustViewport() {
      if (!window.visualViewport) return;
      root.querySelectorAll("dialog[open]").forEach((d) => {
        d.style.maxHeight = Math.max(200, visualViewport.height - 10) + "px";
        if (matchMedia("(max-width:600px)").matches)
          d.style.bottom =
            Math.max(
              0,
              innerHeight - visualViewport.height - visualViewport.offsetTop,
            ) + "px";
      });
    }
    window.visualViewport?.addEventListener("resize", adjustViewport);
    window.visualViewport?.addEventListener("scroll", adjustViewport);
    function setTab(name) {
      root.querySelectorAll("[data-tab]").forEach((b) => {
        const selected = b.dataset.tab === name;
        b.setAttribute("aria-selected", String(selected));
        b.tabIndex = selected ? 0 : -1;
      });
      root
        .querySelectorAll("[data-panel]")
        .forEach((n) => (n.hidden = n.dataset.panel !== name));
      if (name === "publications" && !pubsLoaded) loadPublications();
      if(management && name==='posts'){ $('[data-panel="publications"]').hidden=false;if(!pubsLoaded)loadPublications();}
    }
    root.querySelectorAll("[data-tab]").forEach((b) => {
      b.addEventListener("click", () => setTab(b.dataset.tab));
      b.addEventListener("keydown", (e) => {
        const tabs = [...root.querySelectorAll("[data-tab]")];
        let idx = tabs.indexOf(b);
        if (e.key === "ArrowRight") idx = (idx + 1) % tabs.length;
        else if (e.key === "ArrowLeft")
          idx = (idx + tabs.length - 1) % tabs.length;
        else return;
        e.preventDefault();
        tabs[idx].focus();
        setTab(tabs[idx].dataset.tab);
      });
    });
    function menu(items) {
      const d = el("details", "ds-menu"),
        s = el("summary", "", "⋯");
      s.setAttribute("aria-label", "Gönderi seçenekleri");
      const panel = el("div");
      for (const [label, fn] of items)
        panel.append(
          button(label, "", async () => {
            d.open = false;
            try {
              await fn();
            } catch (e) {
              say(e.message);
            }
          }),
        );
      d.append(s, panel);
      return d;
    }
    async function report(kind, id) {
      if (!confirm("Bu içeriği inceleme için bildirmek istiyor musunuz?"))
        return;
      await api("/reports", "POST", {
        target_type: kind,
        target_id: id,
        reason: "OTHER",
      });
      say("Bildiriminiz inceleme için alındı.");
    }
    function renderPost(p) {
      posts.set(p.id, p);
      const card = el("article", "ds-card");
      card.dataset.postId = p.id;
      card.id = "post-" + p.id;
      if (p.pinned) card.append(el("div", "ds-pin", "⌖ Sabitlenmiş gönderi"));
      const author = el("header", "ds-author");
      if (p.author_photo) {
        const img = el("img", "ds-avatar");
        img.src = p.author_photo;
        img.alt = "";
        author.append(img);
      } else author.append(el("span", "ds-avatar expert-reference-avatar"));
      const copy = el("div", "ds-author-copy"),
        name = el("b", "", p.author_name);
      copy.append(name, el("span", "ds-verified", " ✓"));
      copy.querySelector(".ds-verified").title =
        "Mesleki belgesi doğrulanmış uzman";
      const time = el("time", "", date(p.created_at));
      time.dateTime = p.created_at;
      copy.append(time);
      author.append(copy);
      const options = p.owned
        ? [
            ["Gönderiyi düzenle", () => openComposer(p)],
            [
              "Gönderiyi sil",
              async () => {
                if (!confirm("Bu gönderi silinsin mi?")) return;
                await api("/posts/" + p.id, "DELETE");
                card.remove();
                posts.delete(p.id);
              },
            ],
            [
              p.pinned ? "Sabitlemeyi kaldır" : "Profilde sabitle",
              async () => {
                await api("/posts/" + p.id, "PATCH", {
                  version: p.version,
                  pinned: !p.pinned,
                });
                await loadPosts(true);
              },
            ],
            [
              p.comments_closed ? "Yorumları aç" : "Yorumları kapat",
              async () => {
                const updated = await api("/posts/" + p.id, "PATCH", {
                  version: p.version,
                  comments_closed: !p.comments_closed,
                });
                replacePost(updated);
              },
            ],
          ]
        : [["Şikâyet et", () => report("POST", p.id)]];
      author.append(menu(options));
      card.append(author);
      if (p.status !== "PUBLISHED") {
        card.append(statusBadge(p.status));
        card.append(
          el(
            "p",
            "ds-muted",
            p.status === "PENDING"
              ? "İçerik yayınlanmadan önce inceleniyor. Şu anda yalnızca siz görebilirsiniz."
              : "İçerik yayınlanmadı. Düzenleyip yeniden incelemeye gönderebilirsiniz.",
          ),
        );
      }
      card.append(linkedText(p.text));
      const gallery = p.media.filter(
        (m) => !(p.link_url && m.id === p.cover_media_id),
      );
      if (gallery.length) {
        const grid = el("div", "ds-gallery");
        grid.dataset.count = gallery.length;
        gallery.forEach((m) => {
          const a = el("a");
          a.href = m.url;
          a.target = "_blank";
          a.rel = "noopener";
          const img = el("img");
          img.src = m.url;
          img.alt = "Gönderi görseli";
          img.loading = "lazy";
          a.append(img);
          grid.append(a);
        });
        card.append(grid);
      }
      if (p.link_url)
        card.append(
          linkCard(
            p.link_url,
            p.preview,
            p.media.find((m) => m.id === p.cover_media_id)?.url,
          ),
        );
      const actions = el("div", "ds-actions"),
        like = button(String(p.like_count), "", async () => {
          if (like.disabled) return;
          like.disabled = true;
          try {
            const data = await api("/posts/" + p.id + "/like", "PUT", {
              liked: !p.liked,
            });
            p.liked = data.liked;
            p.like_count = data.like_count;
            like.lastChild.textContent = String(data.like_count);
            like.setAttribute("aria-pressed", String(p.liked));
          } catch (e) {
            say(e.message);
          } finally {
            like.disabled = false;
          }
        });
      like.prepend(document.createTextNode(""));
      like.setAttribute("aria-label", "Beğen");
      like.setAttribute("aria-pressed", String(p.liked));
      actionIcon(like, "heart");
      const comment = button(p.comment_count + " yorum", "", () =>
        toggleComments(card, p),
      );
      actionIcon(comment, "comment");
      comment.setAttribute("aria-expanded", "false");
      comment.dataset.commentsToggle = "";
      const share = button("Bağlantı", "", async () => {
        try {
          const url = new URL(
            "/expert-support/expert/" + expertId,
            location.origin,
          );
          url.searchParams.set("post", p.id);
          await copyLink(url.href);
          say(
            "Gönderi bağlantısı kopyalandı. Görüntülemek için üye girişi gerekir.",
          );
        } catch (e) {
          say(e.message);
        }
      });
      actionIcon(share, "share");
      actions.append(like, comment, share);
      card.append(actions);
      return card;
    }
    function replacePost(p) {
      const previous = feed.querySelector(`[data-post-id="${p.id}"]`);
      if (previous) previous.replaceWith(renderPost(p));
      else feed.prepend(renderPost(p));
    }
    async function loadPosts(reset = false) {
      if (postsLoading) return;
      postsLoading = true;
      const more = $("[data-more-posts]");
      more.disabled = true;
      try {
        if (reset) {
          postCursor = null;
          posts.clear();
        }
        const data = await api(
          "/experts/" +
            expertId +
            "/posts" +
            (postCursor ? "?before=" + postCursor : ""),
        );
        if (reset) feed.replaceChildren();
        if (!feed.children.length && !data.items.length)
          feed.append(
            el(
              "div",
              "ds-empty",
              owner
                ? "İlk bilimsel paylaşımınızı yapın."
                : "Uzman henüz bir gönderi paylaşmamış.",
            ),
          );
        for (const p of data.items) {
          const old = feed.querySelector(`[data-post-id="${p.id}"]`);
          if (old) old.replaceWith(renderPost(p));
          else feed.append(renderPost(p));
        }
        postCursor = data.next_cursor;
        more.hidden = !postCursor;
      } catch (e) {
        say(e.message);
        if (!feed.children.length)
          feed.append(
            button("Gönderileri yeniden yükle", "ds-secondary", () =>
              loadPosts(true),
            ),
          );
      } finally {
        postsLoading = false;
        more.disabled = false;
      }
    }
    $("[data-more-posts]")?.addEventListener("click", () => loadPosts());
    async function toggleComments(card, p) {
      let wrap = card.querySelector(".ds-comments");
      const toggle = card.querySelector("[data-comments-toggle]");
      if (wrap) {
        wrap.hidden = !wrap.hidden;
        toggle.setAttribute("aria-expanded", String(!wrap.hidden));
        return;
      }
      wrap = el("section", "ds-comments");
      toggle.setAttribute("aria-expanded", "true");
      const list = el("div"),
        more = button("Diğer yorumlar", "ds-text-button", () => load()),
        form = el("form", "ds-comment-form"),
        input = el("textarea"),
        context = el(
          "small",
          "",
          p.comments_closed ? "Yorumlar kapalı." : "Görüşünüzü paylaşın",
        ),
        submit = el("button", "ds-primary", "Gönder"),
        cancel = button("Vazgeç", "ds-text-button", () => {
          parent = null;
          edit = null;
          context.textContent = "Görüşünüzü paylaşın";
          input.value = "";
          cancel.hidden = true;
        });
      input.maxLength = 1500;
      input.placeholder = "Bir yorum yazın…";
      input.setAttribute("aria-label", "Yorum metni");
      submit.type = "submit";
      const error = el("p", "ds-error");
      error.hidden = true;
      const bottom = el("div", "ds-comment-submit-row");
      bottom.append(context, cancel, submit);
      form.append(input, bottom, error);
      cancel.hidden = true;
      more.hidden = true;
      wrap.append(list, more, form);
      card.append(wrap);
      if (p.comments_closed) {
        input.disabled = true;
        submit.disabled = true;
      }
      let cursor = 0,
        parent = null,
        edit = null,
        key = uuid();
      function renderComment(c) {
        const row = el("article", "ds-comment");
        row.dataset.commentId = c.id;
        row.dataset.reply = String(!!c.parent_id);
        row.append(
          el("b", "", c.author_name),
          el(
            "small",
            "",
            ` · ${date(c.created_at)}${c.parent_id ? " · Yanıt" : ""}`,
          ),
          el("p", "", c.text),
        );
        if (c.status !== "PUBLISHED") row.append(statusBadge(c.status));
        const tools = el("div", "ds-comment-tools");
        if (!c.parent_id && c.status === "PUBLISHED" && !p.comments_closed)
          tools.append(
            button("Yanıtla", "", () => {
              parent = c.id;
              edit = null;
              context.textContent = c.author_name + " adlı üyeye yanıt";
              cancel.hidden = false;
              input.focus();
            }),
          );
        if (c.owned && !p.comments_closed)
          tools.append(
            button("Düzenle", "", () => {
              edit = c;
              parent = null;
              input.value = c.text;
              context.textContent = "Yorumu düzenliyorsunuz";
              cancel.hidden = false;
              input.focus();
            }),
          );
        if (c.owned || p.owned)
          tools.append(
            button("Sil", "", async () => {
              if (!confirm("Yorum silinsin mi?")) return;
              try {
                await api("/comments/" + c.id, "DELETE");
                row.remove();
              } catch (e) {
                say(e.message);
              }
            }),
          );
        tools.append(
          button("Bildir", "", () =>
            report("COMMENT", c.id).catch((e) => say(e.message)),
          ),
        );
        row.append(tools);
        return row;
      }
      async function load() {
        more.disabled = true;
        try {
          const data = await api(
            "/posts/" + p.id + "/comments?after=" + cursor,
          );
          for (const c of data.items) list.append(renderComment(c));
          cursor = data.next_cursor || cursor;
          more.hidden = !data.next_cursor;
        } catch (e) {
          error.hidden = false;
          error.textContent = e.message;
          more.hidden = false;
          more.textContent = "Yorumları yeniden yükle";
        } finally {
          more.disabled = false;
        }
      }
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        if (!input.value.trim() || submit.disabled) return;
        submit.disabled = true;
        error.hidden = true;
        const previouslyPublished = edit?.status === "PUBLISHED";
        try {
          const data = await api(
            edit ? "/comments/" + edit.id : "/posts/" + p.id + "/comments",
            edit ? "PATCH" : "POST",
            edit
              ? { text: input.value, version: edit.version }
              : { text: input.value, parent_id: parent, idempotency_key: key },
          );
          if (edit)
            list
              .querySelector(`[data-comment-id="${edit.id}"]`)
              ?.replaceWith(renderComment(data));
          else list.append(renderComment(data));
          key = uuid();
          parent = null;
          edit = null;
          input.value = "";
          cancel.hidden = true;
          context.textContent = "Görüşünüzü paylaşın";
          p.comment_count = Math.max(0, p.comment_count + (data.status === "PUBLISHED" ? 1 : 0) - (previouslyPublished ? 1 : 0));
          toggle.lastChild.textContent = p.comment_count + " yorum";
          if (data.status !== "PUBLISHED")
            say(
              labels[data.status] + ": yorumunuz diğer üyelere gösterilmiyor.",
            );
        } catch (e) {
          error.hidden = false;
          error.textContent = e.message;
        } finally {
          submit.disabled = false;
        }
      });
      await load();
      input.focus({ preventScroll: true });
    }

    function renderAttachments() {
      if (!dialog) return;
      const box = $("[data-attachments]");
      box.replaceChildren();
      draft.media.forEach((m, index) => {
        const item = el("div", "ds-attachment"),
          img = el("img");
        img.src = m.url;
        img.alt = "Yükleme önizlemesi";
        item.append(img);
        const footer = el("footer");
        footer.append(
          button("‹", "", () => {
            if (index > 0) {
              [draft.media[index - 1], draft.media[index]] = [
                draft.media[index],
                draft.media[index - 1],
              ];
              renderAttachments();
              saveDraft();
            }
          }),
          el(
            "small",
            "",
            m.error
              ? "Yüklenemedi"
              : m.id
                ? m.cover
                  ? "Kapak"
                  : "Hazır"
                : "Yükleniyor…",
          ),
          button("›", "", () => {
            if (index < draft.media.length - 1) {
              [draft.media[index + 1], draft.media[index]] = [
                draft.media[index],
                draft.media[index + 1],
              ];
              renderAttachments();
              saveDraft();
            }
          }),
          button("×", "", () => {
            if (m.uploading) return;
            draft.media.splice(index, 1);
            if (m.local) URL.revokeObjectURL(m.url);
            renderAttachments();
            saveDraft();
          }),
        );
        footer.children[0].setAttribute("aria-label", "Fotoğrafı önceye taşı");
        footer.children[2].setAttribute("aria-label", "Fotoğrafı sonraya taşı");
        footer.lastChild.setAttribute("aria-label", "Fotoğrafı kaldır");
        item.append(footer);
        if (m.uploading) {
          const progress = el("progress");
          progress.max = 100;
          progress.value = m.progress || 0;
          item.append(progress);
        }
        box.append(item);
      });
    }
    function renderPreview() {
      const box = $("[data-preview]");
      if (!box) return;
      box.replaceChildren();
      $("[data-cover]").hidden = !draft.linkUrl;
      if (draft.linkUrl) {
        const wrap = el("div", "ds-preview-wrap");
        wrap.append(
          linkCard(
            draft.linkUrl,
            draft.preview,
            draft.media.find((m) => m.cover)?.url || draft.preview?.cover?.url,
          ),
        );
        const remove = button("×", "ds-icon", () => {
          removedUrl = draft.linkUrl;
          draft.linkUrl = null;
          draft.preview = null;
          previewSequence++;
          renderPreview();
          saveDraft();
        });
        remove.setAttribute("aria-label", "Bağlantı önizlemesini kaldır");
        wrap.append(remove);
        box.append(wrap);
      }
    }
    function fitText() {
      if (!text) return;
      text.style.height = "auto";
      text.style.height =
        Math.min(text.scrollHeight, Math.max(130, innerHeight * 0.4)) + "px";
      $("[data-counter]").textContent = text.value.length + " / 5000";
    }
    function resetInlineComposer(){
      if(!management)return;
      editing=null;text.value=draft.text;
      $('[data-publish]').textContent='Paylaş';dialog.querySelector('h2').textContent='Yeni gönderi';
      $('[data-photo]').hidden=false;$('[data-link]').hidden=false;$('[data-cover]').hidden=!draft.linkUrl;
      $('[data-edit-mode]').hidden=true;$('[data-edit-cancel]').hidden=true;
      const audience=dialog.querySelector('.ds-inline-audience');if(audience)audience.hidden=false;
      renderAttachments();renderPreview();fitText();
    }
    function openComposer(p = null, initial = "") {
      if (!dialog) return;
      if(management)root.closest('.expert-manage-reference').querySelector('[data-manage-tab="posts"]').click();
      editing = p;
      $('[data-edit-mode]').hidden=!(management&&p);$('[data-edit-cancel]').hidden=!(management&&p);
      const audience=dialog.querySelector('.ds-inline-audience');if(audience)audience.hidden=!!p;
      if (p) {
        text.value = p.text;
        $("[data-attachments]").replaceChildren();
        $("[data-preview]").replaceChildren();
        $("[data-publish]").textContent = "Kaydet";
        $("[data-compose-title]");
        dialog.querySelector("h2").textContent = "Gönderiyi düzenle";
      } else {
        if (initial) {
          draft.text = initial;
          draft.key = uuid();
          saveDraft();
        }
        text.value = draft.text;
        renderAttachments();
        renderPreview();
        $("[data-publish]").textContent = "Paylaş";
        dialog.querySelector("h2").textContent = "Yeni gönderi";
      }
      $("[data-photo]").hidden = !!p;
      $("[data-link]").hidden = !!p;
      $("[data-cover]").hidden = !!p || !draft.linkUrl;
      $("[data-discard]").hidden = !!p;
      $("[data-link-entry]").hidden = true;
      $("[data-compose-error]").hidden = true;
      openDialog(dialog);
      fitText();
      text.focus({ preventScroll: true });
    }
    if (owner) {
      $('[data-edit-cancel]').addEventListener('click',resetInlineComposer);
      $("[data-compose]")?.addEventListener("click", () => openComposer());
      text.addEventListener("input", () => {
        fitText();
        if (editing) return;
        draft.text = text.value;
        saveDraft();
        const match = text.value.match(/https:\/\/[^\s<>]+/);
        const url = match?.[0].replace(/[.,;!?)]+$/, "");
        clearTimeout(previewTimer);
        if (url && href(url) && url !== removedUrl && url !== draft.linkUrl)
          previewTimer = setTimeout(() => fetchPreview(url), 650);
      });
      async function fetchPreview(url) {
        if (editing) return;
        const seq = ++previewSequence;
        draft.linkUrl = url;
        draft.preview = null;
        renderPreview();
        saveDraft();
        try {
          const data = await api("/preview", "POST", { url });
          if (seq !== previewSequence) return;
          draft.preview = data.available ? data : null;
          renderPreview();
          saveDraft();
        } catch (e) {
          if (seq === previewSequence) {
            renderPreview();
            say(e.message + " Bağlantıyı önizlemesiz paylaşabilirsiniz.");
          }
        }
      }
      $("[data-link]").addEventListener("click", () => {
        $("[data-link-entry]").hidden = false;
        $("[data-link-input]").focus();
      });
      $("[data-add-link]").addEventListener("click", () => {
        const url = $("[data-link-input]").value.trim();
        if (!href(url)) {
          say("Geçerli bir HTTPS bağlantısı girin.");
          return;
        }
        removedUrl = null;
        fetchPreview(url);
        $("[data-link-entry]").hidden = true;
      });
      let coverMode = false;
      const fileInput = $("[data-file]");
      $("[data-photo]").addEventListener("click", () => {
        coverMode = false;
        fileInput.multiple = true;
        fileInput.click();
      });
      $("[data-cover]").addEventListener("click", () => {
        coverMode = true;
        fileInput.multiple = false;
        fileInput.click();
      });
      function uploadFile(file, item) {
        return new Promise((resolve, reject) => {
          const data = new FormData();
          data.append("file", file);
          const xhr = new XMLHttpRequest();
          xhr.open("POST", API + "/media");
          xhr.timeout = 60000;
          xhr.setRequestHeader("X-Dental-Social", "1");
          xhr.upload.onprogress = (e) => {
            if (e.lengthComputable) {
              item.progress = (e.loaded / e.total) * 100;
              renderAttachments();
            }
          };
          xhr.onload = () => {
            let data;
            try {
              data = JSON.parse(xhr.responseText);
            } catch {}
            if (xhr.status >= 200 && xhr.status < 300 && data?.id)
              resolve(data);
            else reject(new Error(data?.detail || "Görsel yüklenemedi."));
          };
          xhr.onerror = xhr.ontimeout = () =>
            reject(
              new Error(
                "Bağlantı kesildi. Görseli kaldırıp yeniden seçebilirsiniz.",
              ),
            );
          xhr.send(data);
        });
      }
      fileInput.addEventListener("change", async () => {
        const selected = [...fileInput.files];
        fileInput.value = "";
        for (const file of selected) {
          if (draft.media.length >= 4) {
            say("Bir gönderide en fazla dört görsel olabilir.");
            break;
          }
          if (
            !["image/jpeg", "image/png", "image/webp"].includes(file.type) ||
            file.size > 8 * 1024 * 1024
          ) {
            say(
              "JPEG, PNG veya WebP seçin; her görsel en fazla 8 MB olabilir.",
            );
            continue;
          }
          if (coverMode) draft.media = draft.media.filter((m) => !m.cover);
          const item = {
            url: URL.createObjectURL(file),
            local: true,
            cover: coverMode,
            uploading: true,
          };
          draft.media.push(item);
          uploading++;
          renderAttachments();
          try {
            const data = await uploadFile(file, item);
            URL.revokeObjectURL(item.url);
            item.url = data.url;
            item.id = data.id;
            item.local = false;
          } catch (e) {
            item.error = true;
            say(e.message);
          } finally {
            item.uploading = false;
            uploading--;
            renderAttachments();
            renderPreview();
            saveDraft();
          }
        }
      });
      $("[data-discard]").addEventListener("click", () => {
        if (uploading) {
          say("Görsel yüklemesinin bitmesini bekleyin.");
          return;
        }
        if (!confirm("Taslak temizlensin mi?")) return;
        draft.media
          .filter((m) => m.local)
          .forEach((m) => URL.revokeObjectURL(m.url));
        resetDraft();
        text.value = "";
        removedUrl = null;
        renderAttachments();
        renderPreview();
        fitText();
      });
      $("[data-publish]").addEventListener("click", async () => {
        if (sending) return;
        const error = $("[data-compose-error]");
        error.hidden = true;
        if (uploading) {
          error.textContent = "Görseller yükleniyor. Lütfen bekleyin.";
          error.hidden = false;
          return;
        }
        sending = true;
        const submit = $("[data-publish]");
        submit.disabled = true;
        try {
          let row;
          if (editing) {
            row = await api("/posts/" + editing.id, "PATCH", {
              text: text.value,
              version: editing.version,
            });
          } else {
            draft.text = text.value;
            saveDraft();
            checkDraft();
            const cover = draft.media.find((m) => m.cover);
            const p = {
              text: draft.text,
              idempotency_key: draft.key,
              media_ids: draft.media.map((m) => m.id),
              link_url: draft.linkUrl,
              preview_id: draft.preview?.id || null,
              cover_media_id: cover?.id || null,
            };
            if (p.media_ids.length === 4 && !cover)
              p.cover_media_id = p.media_ids[0];
            row = await api("/posts", "POST", p);
            previewSequence++;
            resetDraft();
          }
          closeDialog(dialog);
          editing = null;
          feed.querySelector(".ds-empty")?.remove();
          replacePost(row);
          setTab("posts");refreshStats().catch(()=>{});
          say(
            row.status === "PUBLISHED"
              ? "Gönderiniz yayınlandı."
              : row.status === "PENDING"
                ? "Gönderiniz incelemeye alındı. Onaylandığında üyeler görebilecek."
                : "Gönderiniz yayınlanmadı. İçeriği düzenleyebilirsiniz.",
          );
        } catch (e) {
          error.textContent = e.message;
          error.hidden = false;
        } finally {
          sending = false;
          submit.disabled = false;
        }
      });
      $("[data-sync]").addEventListener("click", async () => {
        const b = $("[data-sync]"),
          status = $("[data-sync-state]");
        b.disabled = true;
        status.textContent = "Herkese açık yayınlar alınıyor…";
        try {
          const data = await api("/orcid/sync", "POST", {
            orcid: $("[data-orcid]").value,
          });
          status.textContent = data.message;
          await loadPublications(true);
        } catch (e) {
          status.textContent = e.message;
        } finally {
          b.disabled = false;
        }
      });
      const pubDialog = $("[data-publication-dialog]"),
        pubForm = $("[data-publication-form]");
      let publicationId = null,
        matchId = null;
      function openPublication(p = null) {
        publicationId = p?.id || null;
        matchId = null;
        pubForm.reset();
        for (const name of [
          "title",
          "authors",
          "year",
          "journal",
          "doi",
          "url",
          "description",
        ])
          pubForm.elements[name].value = p?.[name] ?? "";
        $("[data-publication-error]").hidden = true;
        pubDialog.querySelector("h2").textContent = p
          ? "Yayını düzenle"
          : "Yayın ekle";
        openDialog(pubDialog);
      }
      $("[data-add-publication]").addEventListener("click", () =>
        openPublication(),
      );
      $("[data-doi]").addEventListener("click", async () => {
        const b = $("[data-doi]");
        b.disabled = true;
        try {
          const data = await api("/doi", "POST", {
            doi: pubForm.elements.doi.value,
          });
          for (const name of [
            "title",
            "authors",
            "year",
            "journal",
            "doi",
            "url",
          ])
            pubForm.elements[name].value = data[name] ?? "";
          matchId = data.match_id;
          $("[data-doi-state]").textContent =
            "DOI kaydıyla eşleşen bilgiler getirildi. Kaydetmeden önce kontrol edin; yazarlık doğrulanmaz.";
        } catch (e) {
          $("[data-doi-state]").textContent = e.message;
        } finally {
          b.disabled = false;
        }
      });
      pubForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const submit = pubForm.querySelector("[type=submit]");
        if (submit.disabled) return;
        submit.disabled = true;
        try {
          const data = Object.fromEntries(new FormData(pubForm));
          data.year = data.year ? Number(data.year) : null;
          data.doi = data.doi || null;
          data.url = data.url || null;
          data.match_id = matchId;
          data.version = publicationId
            ? publications.get(publicationId)?.version
            : null;
          await api(
            "/publications" + (publicationId ? "/" + publicationId : ""),
            publicationId ? "PUT" : "POST",
            data,
          );
          closeDialog(pubDialog);
          await loadPublications(true);
          say("Yayın kaydedildi.");
        } catch (e) {
          $("[data-publication-error]").textContent = e.message;
          $("[data-publication-error]").hidden = false;
        } finally {
          submit.disabled = false;
        }
      });
      root._editPublication = openPublication;
    }
    function renderPublication(p) {
      publications.set(p.id, p);
      const card = el("article", "ds-card");
      card.append(
        el("h3", "", p.title),
        el(
          "div",
          "ds-publication-meta",
          [p.journal, p.year].filter(Boolean).join(" · "),
        ),
      );
      if (p.authors) card.append(el("p", "ds-muted", p.authors));
      card.append(
        el(
          "span",
          "ds-publication-source",
          sourceLabels[p.source] || "Manuel ekleme",
        ),
      );
      if (p.status && p.status !== "PUBLISHED")
        card.append(statusBadge(p.status));
      if (p.description) card.append(el("p", "ds-preserve", p.description));
      const links = el("div", "ds-publication-links");
      if (p.doi)
        links.append(external("https://doi.org/" + p.doi, "DOI: " + p.doi));
      if (p.url) links.append(external(p.url, "Kaynağa git ↗"));
      card.append(links);
      if (owner) {
        const tools = el("div", "ds-publication-tools");
        tools.append(
          button("Gönderi olarak paylaş", "", () => {
            const url = p.url || (p.doi ? "https://doi.org/" + p.doi : "");
            openComposer(null, p.title + (url ? "\n" + url : ""));
            if (url) {
              draft.linkUrl = url;draft.preview = null;renderPreview();saveDraft();
              const seq=++previewSequence;
              api('/publications/'+p.id+'/share-preview','POST').then(data=>{
                if(seq!==previewSequence||draft.linkUrl!==url)return;
                draft.preview=data;renderPreview();saveDraft();
              }).catch(()=>{});
            }
          }),
          button("Düzenle", "", () => root._editPublication(p)),
          button("Kaldır", "", async () => {
            if (!confirm("Yayın profilden kaldırılsın mı?")) return;
            try {
              await api("/publications/" + p.id, "DELETE");
              card.remove();
            } catch (e) {
              say(e.message);
            }
          }),
        );
        card.append(tools);
      }
      return card;
    }
    async function loadPublications(reset = false) {
      if (pubsLoading) return;
      pubsLoading = true;
      const more = $("[data-more-publications]");
      more.disabled = true;
      try {
        if (reset) {
          pubCursor = null;
          pubList.replaceChildren();
          publications.clear();
        }
        const data = await api(
          "/experts/" +
            expertId +
            "/publications" +
            (pubCursor ? "?before=" + pubCursor : ""),
        );
        pubsLoaded = true;
        if(management)$('[data-panel="publications"] .ds-section-head h2').textContent='Yayınlarım ('+data.total+')';
        if (!pubList.children.length && !data.items.length)
          pubList.append(el("div", "ds-empty", "Henüz bir yayın eklenmemiş."));
        for (const p of data.items) pubList.append(renderPublication(p));
        pubCursor = data.next_cursor;
        more.hidden = !pubCursor;
        if (owner && data.sync) {
          $("[data-sync-state]").textContent =
            data.sync.status === "FAILED"
              ? "Son aktarım tamamlanamadı. Manuel yayın ekleyebilirsiniz."
              : data.sync.last_success_at
                ? "Son aktarım: " + date(data.sync.last_success_at + "Z")
                : "";
        }
      } catch (e) {
        say(e.message);
      } finally {
        pubsLoading = false;
        more.disabled = false;
      }
    }
    $("[data-more-publications]").addEventListener("click", () =>
      loadPublications(),
    );
    if (management) {
      const host=root.closest('.expert-manage-reference');
      const general=host.querySelector('[data-manage-pane="general"]');
      const social=host.querySelector('[data-manage-pane="social"]');
      const settings=host.querySelector('[data-manage-pane="settings"]');
      const availability=host.querySelector('.expert-availability-switch');
      if(availability)host.querySelector('[data-manage-availability]').append(availability);
      for(const b of host.querySelectorAll('[data-manage-tab]'))b.addEventListener('click',()=>{
        const name=b.dataset.manageTab;if(name!=='posts'&&editing)resetInlineComposer();
        host.querySelectorAll('[data-manage-tab]').forEach(tab=>tab.setAttribute('aria-selected',String(tab===b)));
        general.hidden=name!=='general';social.hidden=!['posts','publications'].includes(name);settings.hidden=name!=='settings';
        if(!social.hidden)setTab(name);
      });
      const publicationsPanel=$('[data-panel=publications]'),orcid=publicationsPanel.querySelector('.ds-orcid');if(orcid)publicationsPanel.prepend(orcid);
      text.rows=3;text.value=draft.text;renderAttachments();renderPreview();fitText();setTab('posts');
    }
    async function refreshStats(){
      const shell=root.closest('.expert-reference-profile');if(!shell)return;
      const data=await api('/experts/'+expertId+'/stats');
      shell.querySelectorAll('[data-stat]').forEach(n=>n.textContent=data[n.dataset.stat]??'0');
      const follow=shell.querySelector('[data-follow-expert]');if(follow){follow.dataset.followed=String(data.following_by_viewer);follow.textContent=data.following_by_viewer?'Takip ediliyor':'Takip et';follow.setAttribute('aria-pressed',String(data.following_by_viewer));}
    }
    root.closest('.expert-reference-profile')?.addEventListener('click',async event=>{const follow=event.target.closest('[data-follow-expert]');if(!follow||follow.disabled)return;follow.disabled=true;try{await api('/experts/'+expertId+'/follow','PUT',{followed:follow.dataset.followed!=='true'});await refreshStats();}catch(e){say(e.message);}finally{follow.disabled=false;}});
    window.addEventListener('dai:expert-profile-refreshed',()=>refreshStats().catch(()=>{}));
    refreshStats().catch(()=>{});
    loadPosts(true).then(async () => {
      const target = new URLSearchParams(location.search).get("post");
      if (target && /^\d+$/.test(target)) {
        try {
          const p = await api("/posts/" + target);
          if (p.author_id !== expertId) return;
          replacePost(p);
          setTimeout(
            () =>
              feed
                .querySelector(`[data-post-id="${p.id}"]`)
                ?.scrollIntoView({ block: "center", behavior: "smooth" }),
            100,
          );
        } catch (e) {
          say(e.message);
        }
      }
    });
  }
  function mountAll() {
    document.querySelectorAll("[data-expert-social]").forEach(mount);
  }
  window.DentalSocial = { mountAll, api, el, button, labels };
  mountAll();
})();
