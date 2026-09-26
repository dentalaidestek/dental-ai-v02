self.addEventListener("push", event => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (_) {}
  const title = "Dental AI";
  const body = String(data.body || "Dental AI'da yeni bir bildiriminiz var.");
  const targetUrl = (typeof data.target_url === "string" && data.target_url.startsWith("/") && !data.target_url.startsWith("//")) ? data.target_url : "/";
  const noticeId = String(data.notice_id || "");
  event.waitUntil(self.registration.showNotification(title, {
    body,
    tag: noticeId ? "dentalai-notice-" + noticeId : "dentalai-notice",
    renotify: false,
    data: { target_url: targetUrl, notice_id: noticeId }
  }));
});

self.addEventListener("notificationclick", event => {
  event.notification.close();
  const targetUrl = event.notification.data?.target_url || "/";
  event.waitUntil((async () => {
    const target = new URL(targetUrl, self.location.origin);
    const windows = await clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const client of windows) {
      try {
        const current = new URL(client.url);
        if (current.origin === target.origin && current.pathname === target.pathname) {
          await client.focus();
          return;
        }
      } catch (_) {}
    }
    if (clients.openWindow) await clients.openWindow(target.href);
  })());
});
