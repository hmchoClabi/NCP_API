(() => {
  "use strict";

  document.querySelectorAll("[data-retention-policy]").forEach((policy) => {
    const mode = policy.querySelector("[data-retention-mode]");
    const daysLabel = policy.querySelector("[data-retention-days]");
    const days = daysLabel?.querySelector("input");
    const sync = () => {
      const timed = mode?.value === "DAYS";
      if (daysLabel) daysLabel.hidden = !timed;
      if (days) {
        days.disabled = !timed;
        days.required = timed;
      }
    };
    mode?.addEventListener("change", sync);
    sync();
  });

  const cleanupReports = Array.from(
    document.querySelectorAll(".cleanup-report:not(:disabled)")
  );
  const cleanupSelectAll = document.querySelector("#select-all-cleanup-reports");
  const cleanupCount = document.querySelector("#cleanup-selected-count");
  const cleanupSubmit = document.querySelector("[data-cleanup-selected-submit]");
  const syncCleanupSelection = () => {
    const selected = cleanupReports.filter((item) => item.checked).length;
    if (cleanupCount) cleanupCount.textContent = String(selected);
    if (cleanupSubmit) cleanupSubmit.disabled = selected === 0;
    if (cleanupSelectAll) {
      cleanupSelectAll.checked = cleanupReports.length > 0 && selected === cleanupReports.length;
      cleanupSelectAll.indeterminate = selected > 0 && selected < cleanupReports.length;
    }
  };
  cleanupSelectAll?.addEventListener("change", () => {
    cleanupReports.forEach((item) => { item.checked = cleanupSelectAll.checked; });
    syncCleanupSelection();
  });
  cleanupReports.forEach((item) => item.addEventListener("change", syncCleanupSelection));
  syncCleanupSelection();

  const region = document.querySelector(".notification-region");
  if (!region) return;

  const checkpointKey = "ncp-report-notification-checkpoint";
  const seenKey = "ncp-report-notification-seen";
  let savedSeen = [];
  try {
    savedSeen = JSON.parse(window.sessionStorage.getItem(seenKey) || "[]");
  } catch (_) {
    savedSeen = [];
  }
  const seen = new Set(Array.isArray(savedSeen) ? savedSeen : []);
  const lifetimeMs = 6000;

  function dismiss(notification) {
    if (!notification || notification.dataset.closing === "true") return;
    notification.dataset.closing = "true";
    notification.classList.remove("is-visible");
    notification.classList.add("is-leaving");
    window.setTimeout(() => notification.remove(), 320);
  }

  function activate(notification) {
    notification.querySelector(".notification-close")?.addEventListener(
      "click", () => dismiss(notification)
    );
    window.requestAnimationFrame(() => notification.classList.add("is-visible"));
    window.setTimeout(() => dismiss(notification), lifetimeMs);
  }

  function addNotification(event) {
    if (event.id && seen.has(event.id)) return;
    if (event.id) {
      seen.add(event.id);
      try {
        window.sessionStorage.setItem(
          seenKey, JSON.stringify(Array.from(seen).slice(-100))
        );
      } catch (_) {
        // Notifications still work when browser storage is unavailable.
      }
    }
    const notification = document.createElement("div");
    notification.className = `app-notification ${event.category || "info"}`;
    notification.setAttribute("role", "status");

    const icon = document.createElement("span");
    icon.className = "notification-icon";
    icon.setAttribute("aria-hidden", "true");

    const content = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = event.category === "error" ? "작업 오류" : "작업 알림";
    const message = document.createElement("p");
    message.textContent = event.message;
    content.append(title, message);
    if (event.occurred_at_kst) {
      const time = document.createElement("time");
      time.textContent = event.occurred_at_kst;
      content.append(time);
    }

    const close = document.createElement("button");
    close.type = "button";
    close.className = "notification-close";
    close.setAttribute("aria-label", "알림 닫기");
    close.textContent = "×";
    notification.append(icon, content, close);
    region.append(notification);
    activate(notification);
  }

  region.querySelectorAll("[data-server-message]").forEach(activate);

  const endpoint = region.dataset.notificationUrl;
  let checkpoint = region.dataset.notificationSince;
  try {
    checkpoint = window.sessionStorage.getItem(checkpointKey) || checkpoint;
  } catch (_) {
    // Use the server-rendered checkpoint when browser storage is unavailable.
  }
  if (!endpoint || !checkpoint) return;

  async function poll() {
    if (document.hidden) return;
    try {
      const url = new URL(endpoint, window.location.origin);
      url.searchParams.set("after", checkpoint);
      const response = await fetch(url, {
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      });
      if (!response.ok) return;
      const payload = await response.json();
      (payload.events || []).forEach(addNotification);
      if (payload.server_time) {
        checkpoint = payload.server_time;
        try {
          window.sessionStorage.setItem(checkpointKey, checkpoint);
        } catch (_) {
          // Polling remains active without persistent page-to-page state.
        }
      }
    } catch (_) {
      // A transient polling error must not interrupt the current page.
    }
  }

  window.setInterval(poll, 4000);
  poll();
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) poll();
  });
})();
