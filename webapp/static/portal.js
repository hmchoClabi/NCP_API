(() => {
  "use strict";

  const menu = document.querySelector(".menu-toggle");
  const sidebar = document.querySelector(".sidebar");
  if (menu && sidebar) {
    menu.hidden = false;
    const smallScreen = window.matchMedia("(max-width: 1000px)");
    const setMenuOpen = (open) => {
      sidebar.classList.toggle("is-collapsed", !open);
      menu.setAttribute("aria-expanded", String(open));
      menu.textContent = open ? "메뉴 닫기" : "메뉴 열기";
    };
    setMenuOpen(!smallScreen.matches);
    smallScreen.addEventListener("change", () => setMenuOpen(!smallScreen.matches));
    menu.addEventListener("click", () => setMenuOpen(menu.getAttribute("aria-expanded") !== "true"));
    sidebar.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && smallScreen.matches) {
        setMenuOpen(false);
        menu.focus();
      }
    });
  }

  document.querySelectorAll(".table-wrap").forEach((table, index) => {
    const hint = document.createElement("p");
    hint.className = "table-scroll-hint";
    hint.id = `table-scroll-hint-${index}`;
    hint.textContent = "표를 좌우로 스크롤하면 나머지 항목을 볼 수 있습니다.";
    table.before(hint);
    const update = () => {
      const overflowing = table.scrollWidth > table.clientWidth + 1;
      hint.hidden = !overflowing;
      if (overflowing) {
        table.tabIndex = 0;
        table.setAttribute("aria-describedby", hint.id);
      } else {
        table.removeAttribute("tabindex");
        table.removeAttribute("aria-describedby");
      }
    };
    update();
    if (window.ResizeObserver) new ResizeObserver(update).observe(table);
  });

  const reportFrame = document.querySelector(".report-frame");
  const reportButtons = document.querySelectorAll("[data-report-action]");
  if (reportFrame) {
    let reportDocument;
    let beforePrint = [];
    const prepareReport = () => {
      reportDocument = null;
      reportButtons.forEach((button) => { button.disabled = true; });
      try {
        const content = reportFrame.contentDocument;
        if (!content?.querySelector(".report-shell")) return;
        reportDocument = content;
        if (!content.querySelector("#portal-report-display")) {
          const style = content.createElement("style");
          style.id = "portal-report-display";
          style.textContent = document.querySelector("#report-display-style").content.textContent;
          content.head.append(style);
        }
        reportFrame.contentWindow.addEventListener("afterprint", () => {
          beforePrint.forEach(([detail, open]) => { detail.open = open; });
          beforePrint = [];
        });
        reportButtons.forEach((button) => { button.disabled = false; });
      } catch (_) {
        // Authentication redirects or unavailable content keep actions disabled.
      }
    };
    reportFrame.addEventListener("load", prepareReport);
    if (reportFrame.contentDocument?.readyState === "complete") prepareReport();
    reportButtons.forEach((button) => button.addEventListener("click", () => {
      if (!reportDocument) return;
      const details = Array.from(reportDocument.querySelectorAll("details"));
      if (button.dataset.reportAction === "print") {
        beforePrint = details.map((detail) => [detail, detail.open]);
        details.forEach((detail) => { detail.open = true; });
        reportFrame.contentWindow.focus();
        reportFrame.contentWindow.print();
      } else {
        details.forEach((detail) => { detail.open = button.dataset.reportAction === "expand"; });
      }
    }));
  }

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
    if (notification.classList.contains("error")) {
      notification.setAttribute("role", "alert");
      return;
    }
    let timer;
    const pause = () => window.clearTimeout(timer);
    const resume = () => {
      pause();
      if (!notification.matches(":hover, :focus-within")) {
        timer = window.setTimeout(() => dismiss(notification), lifetimeMs);
      }
    };
    notification.addEventListener("pointerenter", pause);
    notification.addEventListener("pointerleave", resume);
    notification.addEventListener("focusin", pause);
    notification.addEventListener("focusout", () => window.setTimeout(resume, 0));
    resume();
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
