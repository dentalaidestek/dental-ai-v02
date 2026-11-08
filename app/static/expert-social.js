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
        const error = new Error(
          typeof message === "string"
            ? message
            : "İşlem tamamlanamadı. Yeniden deneyin.",
        );
        error.status = response.status;
        throw error;
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
  function statusBadge(status, moderation) {
    return el(
      "span",
      "ds-status" + (status === "REJECTED" ? " is-rejected" : status === "PUBLISHED" ? " is-published" : ""),
      status === "PUBLISHED" ? "Yayında" : moderation?.wait_type === 'OWNER_CHANGES' ? 'Düzenleme gerekli' : labels[status] || status,
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
    const description = preview?.site_name && preview?.description?.startsWith(preview.site_name + " · ")
      ? preview.description.slice(preview.site_name.length + 3)
      : preview?.description;
    if (description) body.append(el("p", "", description));
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
  function mediaCarousel(track, count, label) {
    const wrap = el("div", "ds-media-carousel");
    wrap.append(track);
    if (count > 1) {
      track.tabIndex = 0;
      track.setAttribute("aria-label", label);
      const position = el("output", "ds-carousel-position", "1 / " + count);
      position.setAttribute("aria-label", "Görsel konumu");
      track.addEventListener("scroll", () => {
        const stride = track.children[1].offsetLeft - track.children[0].offsetLeft;
        const index = stride ? Math.round(track.scrollLeft / stride) : 0;
        position.textContent = Math.max(1, Math.min(count, index + 1)) + " / " + count;
      }, { passive: true });
      wrap.append(position);
    }
    return wrap;
  }
  const iconPaths = {
    heart:
      "M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z",
    comment:
      "M21 11.5a8.5 8.5 0 0 1-8.5 8.5H4l-3 2 1.5-6A8.5 8.5 0 1 1 21 11.5Z",
    share: "M9 12h12m-4-4 4 4-4 4M13 5H4v14h9",
  };
  function actionIcon(b, name) {
    if (name === "heart") {
      const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      icon.setAttribute("class", "ds-action-icon ds-heart");
      icon.setAttribute("viewBox", "0 0 24 24");
      icon.setAttribute("aria-hidden", "true");
      const path = document.createElementNS(icon.namespaceURI, "path");
      path.setAttribute("d", iconPaths.heart);
      icon.append(path);
      b.prepend(icon);
      return;
    }
    const icons = {comment: "chat-circle-text", share: "share-network"};
    const img = el("img", "ds-action-icon");
    img.src = "/static/expert-icons/" + icons[name] + ".svg";
    img.alt = "";
    b.prepend(img);
  }
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
    const followingFeed=root.dataset.feedMode==='following';
    const notice = $("[data-notice]");
    function say(message, post = null) {
      if (dialog?.open && !post) {
        const error = $("[data-compose-error]");
        error.textContent = message;
        error.hidden = false;
        error.scrollIntoView({block: "nearest"});
        return;
      }
      notice.hidden = false;
      notice.replaceChildren(el("span", "", message));
      if (post) notice.append(button("Gönderiye git", "ds-notice-action", () => showPost(post.id)));
      const dismiss = button("×", "ds-notice-dismiss", () => { notice.hidden = true; });
      dismiss.setAttribute("aria-label", "Bildirimi kapat");
      notice.append(dismiss);
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
      preparingPublication = false,
      previewSequence = 0,
      previewTimer = null,
      removedUrl = null;
    const dialog = $("[data-composer]"),
      text = $("[data-post-text]");
    if(management && dialog)$('[data-panel="posts"]').prepend(dialog);
    let sessionEnding=false;
    window.addEventListener('dai:session-ending',()=>{
      sessionEnding=true;clearTimeout(previewTimer);previewSequence++;
      for(const media of draft.media)if(media.local)URL.revokeObjectURL(media.url);
      draft={text:'',media:[],linkUrl:null,preview:null,key:uuid()};
      if(text)text.value='';
      try{sessionStorage.removeItem(draftKey)}catch{}
    });
    function saveDraft() {
      if (editing||sessionEnding) return;
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
      clearTimeout(previewTimer);
      previewSequence++;
      removedUrl = null;
      preparingPublication = false;
      const submit = $("[data-publish]");
      if (submit && !sending) {
        submit.disabled = false;
        submit.textContent = "Paylaş";
      }
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
    async function report(kind, id, feedback = say) {
      if (!confirm("Bu içeriği inceleme için bildirmek istiyor musunuz?"))
        return;
      await api("/reports", "POST", {
        target_type: kind,
        target_id: id,
        reason: "OTHER",
      });
      feedback("Bildiriminiz inceleme için alındı.");
    }
    function renderPost(p) {
      posts.set(p.id, p);
      if (p.comments_closed) {
        const sheet = root.querySelector(`[data-comments-sheet][data-comment-post-id="${p.id}"]`);
        if (sheet) { closeDialog(sheet); sheet.remove(); }
      }
      const card = el("article", "ds-card");
      card.dataset.postId = p.id;
      card.id = "post-" + p.id;
      const author = el("header", "ds-author");
      if (p.author_photo) {
        const img = el("img", "ds-avatar");
        img.src = p.author_photo;
        img.alt = "";
        author.append(img);
      } else author.append(el("span", "ds-avatar expert-reference-avatar"));
      const copy = el("div", "ds-author-copy"),
        name = el(followingFeed ? "a" : "b", "", p.author_name);
      if(followingFeed)name.href='/expert-support/expert/'+p.author_id;
      copy.append(name, el("span", "ds-verified", " ✓"));
      copy.querySelector(".ds-verified").title =
        "Mesleki belgesi doğrulanmış uzman";
      const time = el("time", "", date(p.created_at));
      time.dateTime = p.created_at;
      const metadata = el("div", "ds-post-meta");
      metadata.append(time);
      if (p.status === "PUBLISHED") metadata.append(statusBadge(p.status));
      if (p.pinned) {
        const pin = el("span", "ds-pin");
        pin.setAttribute("aria-label", "Sabitlenmiş gönderi");
        const icon = el("img"); icon.src = "/static/expert-icons/push-pin.svg"; icon.alt = "";
        pin.append(icon, document.createTextNode("Sabit")); metadata.append(pin);
      }
      copy.append(metadata);
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
      if(p.owned&&p.status!=='PUBLISHED')options.splice(2,1);
      author.append(menu(options));
      card.append(author);
      if (p.status !== "PUBLISHED") {
        const status = el("div", "ds-post-status");
        status.append(statusBadge(p.status,p.moderation));
        const refresh=button('Durumu yenile','ds-text-button',async()=>{
          if(refresh.disabled)return;refresh.disabled=true;
          try{replacePost(await api('/posts/'+p.id));}catch(e){say(e.message);}finally{refresh.disabled=false;}
        });
        status.append(refresh);
        card.append(status, el("p", "ds-muted ds-moderation-reason",
          p.moderation?.reason || (p.status === "PENDING"
            ? "İçerik yayınlanmadan önce inceleniyor. Şu anda yalnızca siz görebilirsiniz."
            : "İçerik yayınlanmadı. Düzenleyip yeniden incelemeye gönderebilirsiniz.")));
      }
      // Older publication shares copied the same title and URL into the text.
      // Keep the saved text editable, but display that exact duplicate only once.
      const duplicatePublication = p.link_url && p.preview?.title &&
        p.text.trim() === p.preview.title.trim() + "\n" + p.link_url;
      if (p.text && !duplicatePublication) card.append(linkedText(p.text));
      const gallery = p.media.filter(
        (m) => !(p.link_url && m.id === p.cover_media_id),
      );
      if (gallery.length) {
        const grid = el("div", "ds-gallery");
        grid.dataset.count = gallery.length;
        gallery.forEach((m,index) => {
          const a = el("button",'ds-gallery-open');a.type='button';
          a.setAttribute('aria-label',`Gönderi görselini aç: ${index+1} / ${gallery.length}`);
          a.addEventListener('click',()=>window.DentalMediaViewer.open(gallery,index,a));
          const img = el("img");
          img.src = m.url;
          img.alt = "Gönderi görseli";
          img.loading = "lazy";
          a.append(img);
          grid.append(a);
        });
        card.append(mediaCarousel(grid, gallery.length, "Gönderi görselleri"));
      }
      if (p.link_url)
        card.append(
          linkCard(
            p.link_url,
            p.preview,
            p.media.find((m) => m.id === p.cover_media_id)?.url,
          ),
        );
      const actionError = el("p", "ds-action-error");
      actionError.hidden = true;
      actionError.setAttribute("role", "status");
      const actions = el("div", "ds-actions"),
        like = button(String(p.like_count), "", async () => {
          if (like.disabled) return;
          actionError.hidden = true;
          like.disabled = true;
          like.setAttribute("aria-busy", "true");
          try {
            const data = await api("/posts/" + p.id + "/like", "PUT", {
              liked: !p.liked,
            });
            p.liked = data.liked;
            p.like_count = data.like_count;
            like.lastChild.textContent = String(data.like_count);
            like.setAttribute("aria-pressed", String(p.liked));
            like.setAttribute("aria-label", p.liked ? "Beğenmekten vazgeç" : "Beğen");
          } catch (e) {
            actionError.textContent = e.message;
            actionError.hidden = false;
            actionError.scrollIntoView({block: "nearest"});
          } finally {
            like.disabled = false;
            like.removeAttribute("aria-busy");
          }
        });
      like.prepend(document.createTextNode(""));
      like.setAttribute("aria-label", p.liked ? "Beğenmekten vazgeç" : "Beğen");
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
            "/expert-support/expert/" + p.author_id,
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
      if(p.status!=='PUBLISHED')like.disabled=comment.disabled=share.disabled=true;
      actions.append(like);
      if (!p.comments_closed) actions.append(comment);
      actions.append(share);
      card.append(actionError, actions);
      if(p.comments_closed){const closed=el('p','ds-comments-state','Yorumlar kapalı');closed.dataset.commentsState='';card.append(closed);}
      return card;
    }
    function replacePost(p) {
      const previous = feed.querySelector(`[data-post-id="${p.id}"]`);
      if (previous) previous.replaceWith(renderPost(p));
      else feed.prepend(renderPost(p));
    }
    function showPost(id) {
      setTab("posts");
      const card = feed.querySelector(`[data-post-id="${id}"]`);
      if (!card) return;
      card.tabIndex = -1;
      card.scrollIntoView({block: "start"});
      card.focus({preventScroll: true});
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
          (followingFeed ? "/feed/following" : "/experts/" +
            expertId +
            "/posts") +
            (postCursor ? "?before=" + postCursor : ""),
        );
        if (reset) feed.replaceChildren();
        if (!feed.children.length && !data.items.length)
          feed.append(
            el(
              "div",
              "ds-empty",
              followingFeed ? "Takip ettiğiniz uzmanların gönderileri burada görünecek." : owner
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
    const commentDrafts=new Map();
    window.addEventListener('dai:session-ending',()=>{commentDrafts.clear();root.querySelector('[data-comments-sheet]')?.close();});
    async function toggleComments(card, p) {
      if (p.comments_closed || posts.get(p.id)?.comments_closed) return;
      const previous=root.querySelector('[data-comments-sheet]');
      if(previous?.open){closeDialog(previous);return;}
      previous?.remove();
      const toggle = card.querySelector("[data-comments-toggle]");
      const wrap = el("dialog", "ds-dialog ds-comments-sheet");
      wrap.dataset.commentsSheet='';wrap.dataset.commentPostId=p.id;wrap.setAttribute('aria-label','Yorumlar');
      toggle.setAttribute("aria-expanded", "true");
      const heading=el('header','ds-dialog-head ds-comments-head'),title=el('h2','','Yorumlar'),total=el('span','ds-comment-total',String(p.comment_count));
      const close=button('×','ds-icon',()=>closeDialog(wrap));close.setAttribute('aria-label','Yorumları kapat');
      heading.append(title,total,close);
      const list = el("div",'ds-comments-list'),
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
      input.rows=1;input.placeholder = "Yorum ekle…";
      input.setAttribute("aria-label", "Yorum metni");
      submit.type = "submit";
      const error = el("p", "ds-error");
      error.hidden = true;
      const bottom = el("div", "ds-comment-submit-row");
      bottom.append(context, cancel, submit);
      form.append(input, bottom, error);
      cancel.hidden = true;
      more.hidden = true;
      const scrollArea=el('div','ds-comments-scroll');scrollArea.append(list,more);
      wrap.append(heading,scrollArea,form);
      root.append(wrap);
      if (p.comments_closed) {
        input.disabled = true;
        submit.disabled = true;
      }
      const savedComment=commentDrafts.get(p.id);
      let cursor = 0,
        parent = savedComment?.parent || null,
        edit = savedComment?.edit || null,
        key = savedComment?.key || uuid(),signature=savedComment?.signature||null,loading=false;
      input.value=savedComment?.text||'';
      if(parent||edit){cancel.hidden=false;context.textContent=edit?'Yorumu düzenliyorsunuz':'Yoruma yanıt';}
      const scroll=window.scrollY,overflow=document.body.style.overflow;
      wrap.addEventListener('cancel',event=>{event.preventDefault();closeDialog(wrap);});
      wrap.addEventListener('click',event=>{if(event.target===wrap)closeDialog(wrap);});
      wrap.addEventListener('close',()=>{
        if(!sessionEnding)commentDrafts.set(p.id,{text:input.value,parent,edit,key,signature});
        else {input.value='';commentDrafts.clear();}
        if(commentDrafts.size>20)commentDrafts.delete(commentDrafts.keys().next().value);
        toggle.setAttribute('aria-expanded','false');document.body.style.overflow=overflow;
        if(!sessionEnding){window.scrollTo(0,scroll);toggle.focus({preventScroll:true});}
      },{once:true});
      let dragStart=null;
      heading.addEventListener('pointerdown',event=>{if(!event.target.closest('button'))dragStart=event.clientY;});
      heading.addEventListener('pointerup',event=>{if(dragStart!==null&&event.clientY-dragStart>75)closeDialog(wrap);dragStart=null;});
      input.addEventListener('input',()=>{input.style.height='auto';input.style.height=Math.min(110,input.scrollHeight)+'px';commentDrafts.set(p.id,{text:input.value,parent,edit,key,signature});});
      function count(value){p.comment_count=value;toggle.lastChild.textContent=value+' yorum';total.textContent=String(value);}
      function inform(message){error.textContent=message;error.hidden=false;}
      function renderComment(c) {
        const row = el("article", "ds-comment");
        row.dataset.commentId = c.id;
        row.dataset.parentId=c.parent_id||'';
        row.dataset.reply = String(!!c.parent_id);
        const author=el('div','ds-comment-author'),identity=el(c.author_profile_url?'a':'span','ds-comment-identity');
        if(c.author_profile_url){identity.href=c.author_profile_url;identity.setAttribute('aria-label',c.author_name);}
        if(c.author_photo){const photo=el('img','ds-comment-avatar');photo.src=c.author_photo;photo.alt='';photo.loading='lazy';identity.append(photo);}
        identity.append(el('b','',c.author_name));
        if(c.author_verified){const badge=el('span','ds-verified','✓');badge.setAttribute('aria-label','Mesleki belgesi doğrulanmış uzman');identity.append(badge);}
        author.append(identity,
          el(
            "small",
            "",
            ` · ${date(c.created_at)}${c.parent_id ? " · Yanıt" : ""}`,
          ));row.append(author,el("p", "", c.text));
        if (c.status !== "PUBLISHED") {row.append(statusBadge(c.status,c.moderation));if(c.moderation?.reason)row.append(el('small','ds-muted',c.moderation.reason));}
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
            button("Sil", "", async (event) => {
              const remove=event.currentTarget;if(remove.disabled)return;
              if (!confirm("Yorum silinsin mi?")) return;
              remove.disabled=true;
              try {
                const result=await api("/comments/" + c.id, "DELETE");
                list.querySelectorAll(`[data-parent-id="${c.id}"]`).forEach(reply=>reply.remove());
                row.remove();
                count(result.comment_count);
                if(parent===c.id||edit?.id===c.id){parent=null;edit=null;cancel.hidden=true;context.textContent='Görüşünüzü paylaşın';}
              } catch (e) {
                inform(e.message);
              }finally{remove.disabled=false;}
            }),
          );
        tools.append(
          button("Bildir", "", () =>
            report("COMMENT", c.id,inform).catch((e) => inform(e.message)),
          ),
        );
        row.append(tools);
        return row;
      }
      async function load() {
        if(loading)return;loading=true;
        more.disabled = true;
        try {
          const data = await api(
            "/posts/" + p.id + "/comments?after=" + cursor,
          );
          for (const c of data.items) list.append(renderComment(c));
          if(data.comment_count!==undefined)count(data.comment_count);
          if(!list.children.length)list.append(el('p','ds-comments-empty','İlk yorumu siz yazın.'));
          cursor = data.next_cursor || cursor;
          more.hidden = !data.next_cursor;
        } catch (e) {
          error.hidden = false;
          error.textContent = e.message;
          more.hidden = false;
          more.textContent = "Yorumları yeniden yükle";
        } finally {
          loading=false;
          more.disabled = false;
        }
      }
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        if (!input.value.trim() || submit.disabled) return;
        submit.disabled = true;
        error.hidden = true;
        const previouslyPublished = edit?.status === "PUBLISHED";
        const submitted=input.value;
        const submittedParent=parent,submittedEdit=edit?.id;
        const nextSignature=JSON.stringify([submitted,parent]);
        if(signature&&signature!==nextSignature)key=uuid();signature=nextSignature;
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
          else {list.querySelector('.ds-comments-empty')?.remove();list.append(renderComment(data));}
          key = uuid();
          parent = null;
          edit = null;
          if(input.value===submitted)input.value = "";
          cancel.hidden = true;
          context.textContent = "Görüşünüzü paylaşın";
          count(Math.max(0, p.comment_count + (data.status === "PUBLISHED" ? 1 : 0) - (previouslyPublished ? 1 : 0)));
          const stored=commentDrafts.get(p.id);
          if(stored?.text===submitted&&stored.parent===submittedParent&&stored.edit?.id===submittedEdit)
            commentDrafts.delete(p.id);
          if (data.status !== "PUBLISHED")
            inform(
              labels[data.status] + ": yorumunuz diğer üyelere gösterilmiyor.",
            );
        } catch (e) {
          error.hidden = false;
          error.textContent = e.message;
        } finally {
          submit.disabled = false;
        }
      });
      openDialog(wrap);document.body.style.overflow='hidden';
      await load();
    }

    function removeMedia(media) {
      if (media.uploading) return;
      const index = draft.media.indexOf(media);
      if (index < 0) return;
      draft.media.splice(index, 1);
      if (media.local) URL.revokeObjectURL(media.url);
      renderAttachments();
      renderPreview();
      saveDraft();
    }
    function renderAttachments() {
      if (!dialog) return;
      const box = $("[data-attachments]");
      box.replaceChildren();
      const photos = draft.media.filter((m) => !(draft.linkUrl && m.cover));
      if (!photos.length) return;
      const track = el("div", "ds-attachments-track");
      photos.forEach((m, index) => {
        const item = el("div", "ds-attachment"),
          img = el("img");
        img.src = m.url;
        img.alt = "Yükleme önizlemesi";
        item.append(img);
        const footer = el("footer");
        footer.append(
          button("‹", "", () => {
            if (index > 0) {
              const current = draft.media.indexOf(m), previous = draft.media.indexOf(photos[index - 1]);
              [draft.media[previous], draft.media[current]] = [m, photos[index - 1]];
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
            if (index < photos.length - 1) {
              const current = draft.media.indexOf(m), next = draft.media.indexOf(photos[index + 1]);
              [draft.media[next], draft.media[current]] = [m, photos[index + 1]];
              renderAttachments();
              saveDraft();
            }
          }),
          button("×", "", () => removeMedia(m)),
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
        track.append(item);
      });
      box.append(mediaCarousel(track, photos.length, "Yükleme önizlemeleri"));
    }
    function renderPreview() {
      const box = $("[data-preview]");
      if (!box) return;
      box.replaceChildren();
      $("[data-cover]").hidden = !draft.linkUrl;
      const cover = draft.media.find((m) => m.cover);
      $("[data-cover]").disabled = !!cover?.uploading;
      $("[data-cover] span").textContent = cover ? "Kapağı değiştir" : "Kapak ekle";
      if (draft.linkUrl) {
        const wrap = el("div", "ds-preview-wrap");
        wrap.append(
          linkCard(
            draft.linkUrl,
            draft.preview,
            cover?.url || draft.preview?.cover?.url,
          ),
        );
        const remove = button("×", "ds-icon", () => {
          removedUrl = draft.linkUrl;
          draft.linkUrl = null;
          draft.preview = null;
          draft.media.forEach((media) => { media.cover = false; });
          previewSequence++;
          preparingPublication = false;
          if (!sending) {
            $("[data-publish]").disabled = false;
            $("[data-publish]").textContent = "Paylaş";
          }
          renderAttachments();
          renderPreview();
          saveDraft();
        });
        remove.setAttribute("aria-label", "Bağlantı önizlemesini kaldır");
        wrap.append(remove);
        if (cover) {
          const controls = el("div", "ds-cover-tools");
          const state = el("small", "", cover.error ? "Kapak yüklenemedi" : cover.uploading ? "Kapak yükleniyor…" : "Kapak eklendi");
          state.setAttribute("role", "status");
          const removeCover = button("Kapağı kaldır", "ds-text-button", () => removeMedia(cover));
          removeCover.disabled = !!cover.uploading;
          controls.append(state, removeCover);
          wrap.append(controls);
          if (cover.uploading) {
            const progress = el("progress", "ds-cover-progress");
            progress.setAttribute("aria-label", "Kapak yükleme ilerlemesi");
            progress.max = 100;
            progress.value = cover.progress || 0;
            wrap.append(progress);
          }
        }
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
        preparingPublication = false;
        $("[data-publish]").disabled = sending;
        if (!sending) $("[data-publish]").textContent = "Paylaş";
        const seq = ++previewSequence;
        notice.hidden = true;
        notice.textContent = "";
        $("[data-compose-error]").hidden = true;
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
            const rejected = [400, 401, 403, 422].includes(e.status);
            if (rejected) {
              draft.linkUrl = null;
              draft.preview = null;
              saveDraft();
            }
            renderPreview();
            say(
              e.message +
                (rejected ? "" : " Bağlantıyı önizlemesiz paylaşabilirsiniz."),
            );
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
              if (item.cover) renderPreview();
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
        const selectedAsCover = coverMode;
        fileInput.value = "";
        for (const file of selected) {
          if (draft.media.length - (selectedAsCover && draft.media.some(m => m.cover) ? 1 : 0) >= 4) {
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
          if (selectedAsCover) draft.media = draft.media.filter((m) => !m.cover);
          const item = {
            url: URL.createObjectURL(file),
            local: true,
            cover: selectedAsCover,
            uploading: true,
          };
          draft.media.push(item);
          uploading++;
          renderAttachments();
          renderPreview();
          try {
            const data = await uploadFile(file, item);
            URL.revokeObjectURL(item.url);
            item.url = data.url;
            item.id = data.id;
            item.local = false;
          } catch (e) {
            item.error = true;
            const error = $("[data-compose-error]");
            error.textContent = e.message;
            error.hidden = false;
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
        if (sending || preparingPublication) return;
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
        const wasEditing = !!editing;
        submit.textContent = wasEditing ? "Kaydediliyor…" : "Paylaşılıyor…";
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
              ? "Yayımlandı. Gönderiniz profilinizde."
              : row.status === "PENDING"
                ? "İncelemeye alındı. Onaylanana kadar yalnızca siz görebilirsiniz."
                : "Yayımlanmadı. Gönderideki gerekçeye göre düzenleyebilirsiniz.",
            row,
          );
          showPost(row.id);
        } catch (e) {
          error.textContent = e.message;
          error.hidden = false;
          error.scrollIntoView({block: "nearest"});
        } finally {
          sending = false;
          submit.disabled = false;
          submit.textContent = editing ? "Kaydet" : "Paylaş";
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
      if (p.status && p.status !== "PUBLISHED") {
        card.append(statusBadge(p.status,p.moderation));
        if(p.moderation?.reason)card.append(el('p','ds-muted',p.moderation.reason));
      }
      if (p.description) card.append(el("p", "ds-preserve", p.description));
      const links = el("div", "ds-publication-links");
      if (p.doi)
        links.append(external("https://doi.org/" + p.doi, "DOI: " + p.doi));
      if (p.url) links.append(external(p.url, "Kaynağa git ↗"));
      card.append(links);
      if (owner) {
        const tools = el("div", "ds-publication-tools");
        tools.append(
          button("Gönderi olarak paylaş", "", async () => {
            const url = p.url || (p.doi ? "https://doi.org/" + p.doi : "");
            if (url && draft.linkUrl === url) { openComposer(); return; }
            if ((draft.text.trim() || draft.media.length || draft.linkUrl) &&
                !confirm("Mevcut taslağın yerine bu yayını paylaşmak ister misiniz?")) return;
            resetDraft();
            draft.text = url ? "" : p.title;
            draft.linkUrl = url || null;
            draft.preview = url ? {title: p.title, site_name: p.journal || "Akademik yayın", description: p.year ? String(p.year) : ""} : null;
            saveDraft();
            openComposer();
            if (url) {
              const seq=++previewSequence;
              const submit = $("[data-publish]");
              preparingPublication = true;
              submit.disabled = true;
              submit.textContent = "Hazırlanıyor…";
              try {
                const data = await api('/publications/'+p.id+'/share-preview','POST');
                if(seq!==previewSequence||draft.linkUrl!==url)return;
                draft.preview=data;renderPreview();saveDraft();
              } catch {
                // A safe source URL remains shareable when metadata is unavailable.
                if (seq === previewSequence) { draft.preview = null; renderPreview(); saveDraft(); }
              } finally {
                if (seq === previewSequence) {
                  preparingPublication = false;
                  submit.disabled = false;
                  submit.textContent = "Paylaş";
                }
              }
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
    $("[data-more-publications]")?.addEventListener("click", () =>
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
      text.rows=2;text.value=draft.text;renderAttachments();renderPreview();fitText();setTab('posts');
    }
    async function refreshStats(){
      const shell=root.closest('.expert-reference-profile');if(!shell)return;
      const data=await api('/experts/'+expertId+'/stats');
      shell.querySelectorAll('[data-stat]').forEach(n=>n.textContent=data[n.dataset.stat]??'0');
      const follow=shell.querySelector('[data-follow-expert]');if(follow){follow.dataset.followed=String(data.following_by_viewer);follow.textContent=data.following_by_viewer?'Takip ediliyor':'Takip et';follow.setAttribute('aria-pressed',String(data.following_by_viewer));}
    }
    const relationshipsDialog=$('[data-relationships-dialog]');
    let relationshipKind=null,relationshipCursor=null,relationshipsLoading=false;
    async function loadRelationships(reset=false){
      if(relationshipsLoading)return;relationshipsLoading=true;
      const list=$('[data-relationships-list]'),more=$('[data-relationships-more]'),error=$('[data-relationships-error]');
      more.disabled=true;error.hidden=true;
      try{
        if(reset){relationshipCursor=null;list.replaceChildren();}
        const data=await api('/experts/'+expertId+'/'+relationshipKind+(relationshipCursor?'?before='+relationshipCursor:''));
        for(const member of data.items){
          const row=el('div','ds-relationship-row'),copy=el(member.profile_url?'a':'span','ds-relationship-copy');
          if(member.profile_url)copy.href=member.profile_url;
          copy.append(el('b','',member.name));if(member.specialty)copy.append(el('small','ds-muted',member.specialty));
          row.append(copy);
          if(member.is_expert&&member.user_id!==userId){
            const follow=button(member.following_by_viewer?'Takip ediliyor':'Takip et','ds-secondary',async()=>{
              if(follow.disabled)return;follow.disabled=true;
              try{const updated=await api('/experts/'+member.user_id+'/follow','PUT',{followed:!member.following_by_viewer});member.following_by_viewer=updated.following_by_viewer;follow.textContent=updated.following_by_viewer?'Takip ediliyor':'Takip et';follow.setAttribute('aria-pressed',String(updated.following_by_viewer));await refreshStats();}
              catch(e){error.hidden=false;error.textContent=e.message;}finally{follow.disabled=false;}
            });follow.setAttribute('aria-pressed',String(member.following_by_viewer));row.append(follow);
          }
          list.append(row);
        }
        if(!list.children.length)list.append(el('p','ds-empty',relationshipKind==='followers'?'Henüz takipçiniz yok.':'Henüz bir uzmanı takip etmiyorsunuz.'));
        relationshipCursor=data.next_cursor;more.hidden=!relationshipCursor;
      }catch(e){error.hidden=false;error.textContent=e.message;more.hidden=false;more.textContent='Yeniden dene';}
      finally{relationshipsLoading=false;more.disabled=false;}
    }
    root.closest('.expert-reference-profile')?.addEventListener('click',event=>{
      const control=event.target.closest('[data-relationships]');if(!control||!relationshipsDialog||relationshipsLoading)return;
      relationshipKind=control.dataset.relationships;
      $('#ds-relationships-title').textContent=relationshipKind==='followers'?'Takipçiler':'Takip edilenler';
      $('[data-relationships-more]').textContent='Daha fazla';openDialog(relationshipsDialog);loadRelationships(true);
    });
    $('[data-relationships-more]')?.addEventListener('click',()=>loadRelationships());
    root.closest('.expert-reference-profile')?.addEventListener('click',async event=>{const follow=event.target.closest('[data-follow-expert]');if(!follow||follow.disabled)return;follow.disabled=true;try{await api('/experts/'+expertId+'/follow','PUT',{followed:follow.dataset.followed!=='true'});await refreshStats();}catch(e){say(e.message);}finally{follow.disabled=false;}});
    window.addEventListener('dai:expert-profile-refreshed',()=>refreshStats().catch(()=>{}));
    refreshStats().catch(()=>{});
    if(new URLSearchParams(location.search).get("tab")==="publications")setTab("publications");
    loadPosts(true).then(async () => {
      const target = new URLSearchParams(location.search).get("post");
      if (target && /^\d+$/.test(target)) {
        try {
          const p = await api("/posts/" + target);
          if (followingFeed || p.author_id !== expertId) return;
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
