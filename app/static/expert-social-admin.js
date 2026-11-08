(() => {
  "use strict";
  const root = document.querySelector("[data-social-admin]");
  if (!root) return;
  const { api, el, button, labels } = window.DentalSocial,
    $ = (q) => root.querySelector(q),
    list = $("[data-admin-list]");
  let cursor = null,
    mode = "queue",loading=false;
  const waitLabels={HUMAN_REVIEW:'Yönetici incelemesi',OWNER_CHANGES:'Uzmandan düzenleme bekleniyor',RETRY:'Otomatik kontrol yeniden denenecek',RETRY_EXHAUSTED:'Otomatik kontrol için müdahale gerekiyor'};
  function elapsed(seconds){return seconds>=86400?Math.floor(seconds/86400)+' gün':seconds>=3600?Math.floor(seconds/3600)+' saat':Math.floor(seconds/60)+' dk';}
  const explain = (m) => {
    $("[data-admin-notice]").hidden = false;
    $("[data-admin-notice]").textContent = m;
  };
  function render(p, kind) {
    const card = el("article", "ds-card");
    card.append(
      el(
        "h3",
        "",
        `${kind === "POST" ? "Gönderi" : kind === "COMMENT" ? "Yorum" : "Akademik yayın"} #${p.id} · ${labels[p.status]}`,
      ),
      el("b", "", p.author_name),
      el(
        "p",
        "ds-preserve",
        p.text ||
          [p.title, p.authors, p.description].filter(Boolean).join("\n"),
      ),
    );
    if(p.moderation){const m=p.moderation;card.append(el('p','ds-admin-wait',(waitLabels[m.wait_type]||'Kontrol tamamlandı')+(p.status==='PENDING'?' · '+elapsed(m.age_seconds)+' bekliyor':'')),el('p','ds-muted',m.reason));}
    if (p.link_url) {
      const a = el("a", "", p.link_url);
      a.href = p.link_url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      card.append(a);
    }
    for (const [index,media] of (p.media || []).entries()) {
      const a = button('', 'ds-media-review',()=>window.DentalMediaViewer.open(p.media,index,a));
      a.setAttribute('aria-label','İncelenecek görseli aç: '+(index+1));
      const img = el("img");
      img.src = media.url;
      img.alt = "İncelenecek görsel";
      img.style.maxWidth = "100%";
      img.style.maxHeight = "340px";
      a.append(img);
      card.append(a);
    }
    const tools = el("div", "ds-review-tools"),
      reason = el("input");
    reason.placeholder = "Kişisel veri içermeyen karar gerekçesi";
    reason.maxLength = 300;
    reason.setAttribute("aria-label", "Karar gerekçesi");
    tools.append(reason);
    for (const [status, label] of [
      ["PUBLISHED", "Yayınla"],
      ["PENDING", "Düzenleme iste"],
      ["REJECTED", "Reddet"],
    ])
      tools.append(
        button(label, "ds-secondary", async () => {
          if (reason.value.trim().length < 3) {
            explain("Kısa bir karar gerekçesi girin.");
            return;
          }
          const buttons = [...tools.querySelectorAll("button")];
          buttons.forEach((b) => (b.disabled = true));
          try {
            await api("/moderation/" + kind + "/" + p.id, "POST", {
              status,
              version: p.version,
              reason: reason.value.trim(),
            });
            card.remove();
            explain(status==='PUBLISHED'?'Gönderi yayında.':status==='PENDING'?'Düzenleme isteği iletildi.':'İçerik reddedildi.');
          } catch (e) {
            explain(e.message);
          } finally {
            buttons.forEach((b) => (b.disabled = false));
          }
        }),
      );
    card.append(tools);
    const history = el("details"),
      summary = el("summary", "", "Karar geçmişi"),
      body = el("div");
    history.append(summary, body);
    history.addEventListener("toggle", async () => {
      if (!history.open || body.childElementCount) return;
      try {
        const data = await api("/moderation/" + kind + "/" + p.id);
        const task=data.item.moderation;
        if(task)body.append(el('p','ds-muted','İş kimliği: '+(task.job_id||'Eski kayıt')+' · İçerik sürümü: '+task.content_version));
        for (const h of data.history)
          body.append(
            el(
              "p",
              "ds-muted",
              `${h.created_at} · ${h.actor_id ? "Yönetici/üye #" + h.actor_id : "Otomatik denetim"} · v${h.version} · ${labels[h.status] || h.status} · ${h.reason}`,
            ),
          );
        for(const h of data.moderation_history||[])body.append(el('p','ds-muted',`${h.created_at} · ${h.source} · ${h.state} · ${h.reason}`));
      } catch (e) {
        explain(e.message);
      }
    });
    card.append(history);
    return card;
  }
  async function load(reset = true) {
    if(loading)return;loading=true;
    if (reset) {
      cursor = null;
      list.replaceChildren();
    }
    const more = $("[data-admin-more]");
    more.disabled = true;
    try {
      if (mode === "reports") {
        const data = await api(
          "/reports" + (cursor ? "?before=" + cursor : ""),
        );
        for (const report of data.items) {
          const item = el("article", "ds-card");
          item.append(
            el("b", "", `Bildirim #${report.id} · ${report.reason}`),
            el(
              "p",
              "ds-muted",
              `Üye #${report.reporter_id} · ${report.created_at}`,
            ),
            button("İçeriği ve geçmişini aç", "ds-secondary", async () => {
              try {
                const data = await api(
                  "/moderation/" + report.target_type + "/" + report.target_id,
                );
                item.replaceWith(render(data.item, report.target_type));
              } catch (e) {
                explain(e.message);
              }
            }),
          );
          list.append(item);
        }
        cursor = data.next_cursor;
      } else {
        const kind = $("[data-kind]").value,
          status = $("[data-status]").value,
          data = await api(
            "/moderation?kind=" +
              kind +
              "&status=" +
              status +
              (cursor ? "&before=" + cursor : ""),
          );
        for (const p of data.items) list.append(render(p, kind));
        cursor = data.next_cursor;
        const aging=$('[data-queue-aging]');
        if(aging&&data.aging){aging.hidden=false;aging.textContent=`Yönetici bekleyen: ${data.aging.waiting_human} · Düzenleme bekleyen: ${data.aging.waiting_owner} · İşlem hatası: ${data.aging.failed} · 1 saati aşan: ${data.aging.over_1h} · 24 saati aşan: ${data.aging.over_24h}`;}
      }
      more.hidden = !cursor;
      if (!list.children.length)
        list.append(el("p", "ds-empty", "Bu listede kayıt yok."));
    } catch (e) {
      explain(e.message);
    } finally {
      loading=false;
      more.disabled = false;
    }
  }
  $("[data-queue]").addEventListener("click", () => {
    mode = "queue";
    load();
  });
  $("[data-reports]").addEventListener("click", () => {
    mode = "reports";
    load();
  });
  $("[data-admin-more]").addEventListener("click", () => load(false));
  load();
})();
