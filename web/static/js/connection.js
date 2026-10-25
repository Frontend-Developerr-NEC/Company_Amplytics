/**
 * Toggles body.is-online / body.is-offline from navigator.onLine
 * and online/offline window events. Updates the offline banner.
 */
(function () {
  const ONLINE = "is-online";
  const OFFLINE = "is-offline";
  const RECONNECTED = "just-reconnected";
  let reconnectTimer = null;

  function setConnectionState(online) {
    const body = document.body;
    const wasOffline = body.classList.contains(OFFLINE);

    body.classList.toggle(ONLINE, online);
    body.classList.toggle(OFFLINE, !online);

    const banner = document.getElementById("connection-banner");
    if (banner) {
      banner.setAttribute("aria-hidden", online ? "true" : "false");
    }

    if (online && wasOffline) {
      body.classList.add(RECONNECTED);
      clearTimeout(reconnectTimer);
      reconnectTimer = setTimeout(() => body.classList.remove(RECONNECTED), 1200);
    }
  }

  function init() {
    setConnectionState(navigator.onLine);

    window.addEventListener("online", () => setConnectionState(true));
    window.addEventListener("offline", () => setConnectionState(false));

    const retry = document.getElementById("connection-retry");
    if (retry) {
      retry.addEventListener("click", () => {
        if (navigator.onLine) {
          setConnectionState(true);
        } else {
          // Soft probe: reload only if browser thinks we're back
          location.reload();
        }
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
