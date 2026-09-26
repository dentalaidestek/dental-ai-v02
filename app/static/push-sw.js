self.addEventListener("push", event => {
  event.waitUntil((async () => {
    let data = {};
    try { data = event.data ? event.data.json() : {}; } catch (_) {}
    const visibleClients = await clients.matchAll({ type: "window", includeUncontrolled: true });
    if (visibleClients.some(client => client.visibilityState === "visible")) return;

    const title = "Dental AI";
    const body = String(data.body || "Dental AI'da yeni bir bildiriminiz var.");
    const targetUrl = (typeof data.target_url === "string" && data.target_url.startsWith("/") && !data.target_url.startsWith("//")) ? data.target_url : "/";
    const noticeId = String(data.notice_id || "");
    const messageEventId = String(data.message_event_id || "");
    const notificationTag = noticeId ? "dentalai-notice-" + noticeId : (messageEventId ? "dentalai-message-" + messageEventId : "dentalai-notification");
    await self.registration.showNotification(title, {
      body,
      tag: notificationTag,
      renotify: false,
      data: { target_url: targetUrl, notice_id: noticeId }
    });
  })());
});

self.addEventListener("notificationclick", event => {
  event.notification.close();
  const rawTarget = event.notification.data?.target_url || "/";
  event.waitUntil((async () => {
    const target = new URL(rawTarget, self.location.origin);
    if (target.origin !== self.location.origin) return;
    const windows = await clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const client of windows) {
      try {
        const current = new URL(client.url);
        if (current.origin !== target.origin) continue;
        if (client.navigate && client.url !== target.href) await client.navigate(target.href);
        await client.focus();
        return;
      } catch (_) {}
    }
    if (clients.openWindow) await clients.openWindow(target.href);
  })());
});
