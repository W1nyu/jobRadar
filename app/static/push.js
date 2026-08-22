/* M9 관리자 화면의 명시적 Web Push 구독 버튼. */
const button = document.querySelector("[data-push-subscribe]");

if (button) {
  button.addEventListener("click", async () => {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
      button.textContent = "이 브라우저는 알림을 지원하지 않습니다";
      return;
    }
    const permission = await Notification.requestPermission();
    if (permission !== "granted") {
      button.textContent = "알림 권한이 필요합니다";
      return;
    }
    const publicKey = await (await fetch("/api/v1/push/public-key")).json();
    const registration = await navigator.serviceWorker.register("/sw.js");
    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: base64ToUint8Array(publicKey.public_key),
    });
    const response = await fetch("/api/v1/push/subscribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(subscription),
    });
    button.textContent = response.ok ? "브라우저 알림이 연결되었습니다" : "알림 연결에 실패했습니다";
  });
}

function base64ToUint8Array(value) {
  const normalized = `${value}`.replace(/-/g, "+").replace(/_/g, "/");
  const padding = "=".repeat((4 - (normalized.length % 4)) % 4);
  const raw = atob(normalized + padding);
  return Uint8Array.from(raw, (character) => character.charCodeAt(0));
}
