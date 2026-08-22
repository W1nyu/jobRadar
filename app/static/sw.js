/* M9 Web Push를 브라우저가 닫혀 있어도 표시하는 Service Worker. */
self.addEventListener("push", (event) => {
  const data = event.data ? event.data.json() : {};
  const title = data.title || "jobRadar";
  event.waitUntil(
    self.registration.showNotification(title, {
      body: data.body || "새 채용공고가 있습니다.",
      tag: data.tag || "jobradar",
      data: { url: data.url || "/admin" },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(clients.openWindow(event.notification.data.url));
});
