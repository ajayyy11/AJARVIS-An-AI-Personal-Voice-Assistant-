(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const log = $("chatLog");
  const statusButton = $("systemStatusButton");
  const statusPanel = $("systemStatusPanel");
  const statusValue = $("serverStatus");
  const statusSummary = $("serverStats");
  const statusMini = $("systemStatusMini");
  const coreStatus = $("coreStatusText");
  const username = document.body.dataset.user || "there";

  function closeStatusPanel() {
    if (!statusPanel || !statusButton) return;
    statusPanel.hidden = true;
    statusButton.setAttribute("aria-expanded", "false");
  }

  if (statusButton && statusPanel) {
    statusButton.addEventListener("click", () => {
      const opening = statusPanel.hidden;
      statusPanel.hidden = !opening;
      statusButton.setAttribute("aria-expanded", String(opening));
    });
    document.addEventListener("click", (event) => {
      if (!statusPanel.contains(event.target) && !statusButton.contains(event.target)) closeStatusPanel();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeStatusPanel();
    });
  }

  function syncStatus() {
    const label = statusValue ? statusValue.textContent.trim() : "Status unavailable";
    if (statusMini) statusMini.textContent = label;
    if (coreStatus) {
      const state = label.toLowerCase();
      coreStatus.textContent = state.includes("operational") ? "READY TO ASSIST"
        : state.includes("limited") ? "LIMITED METRICS" : state.includes("unavailable") ? "STATUS UNAVAILABLE" : "CONNECTING";
    }
    if (statusSummary) statusSummary.setAttribute("title", statusSummary.textContent.trim());
  }
  if (statusValue && "MutationObserver" in window) {
    new MutationObserver(syncStatus).observe(statusValue, { childList: true, characterData: true, subtree: true });
    if (statusSummary) new MutationObserver(syncStatus).observe(statusSummary, { childList: true, characterData: true, subtree: true });
  }
  syncStatus();

  function appendMessage(role, value) {
    const row = document.createElement("div");
    row.className = "chat-message " + (role === "user" ? "user-message" : "assistant-message");
    const orb = document.createElement("span");
    orb.className = "message-orb";
    orb.textContent = role === "user" ? username.slice(0, 1).toUpperCase() : "A";
    const content = document.createElement("div");
    const label = document.createElement("small");
    label.textContent = role === "user" ? "YOU" : "AJARVIS";
    const message = document.createElement("p");
    message.textContent = String(value || "");
    content.append(label, message);
    row.append(orb, content);
    log.appendChild(row);
  }

  const newChatButton = $("newChatButton");
  if (newChatButton && log) {
    newChatButton.addEventListener("click", () => {
      log.replaceChildren();
      appendMessage("assistant", "Hello " + username + ". Your new conversation is ready. What would you like to do?");
      log.dataset.historyLoaded = "true";
      const input = $("commandInput");
      if (input) {
        input.value = "";
        input.focus();
      }
      document.querySelectorAll(".nav-link").forEach((item) => item.classList.remove("is-active"));
      newChatButton.classList.add("is-active");
      $("commandConsole")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  const historyButton = $("chatHistoryButton");
  if (historyButton && log) {
    historyButton.addEventListener("click", async () => {
      historyButton.disabled = true;
      historyButton.textContent = "Loading history…";
      try {
        const response = await fetch("/api/history", { credentials: "same-origin", cache: "no-store" });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "History is unavailable.");
        log.replaceChildren();
        const rows = Array.isArray(result.history) ? result.history.slice().reverse() : [];
        if (!rows.length) {
          appendMessage("assistant", "No previous conversations yet. Start a new chat whenever you're ready.");
        } else {
          rows.forEach((entry) => {
            appendMessage("user", entry.command || "");
            appendMessage("assistant", entry.response || "");
          });
        }
        log.dataset.historyLoaded = "true";
        document.querySelectorAll(".nav-link").forEach((item) => item.classList.remove("is-active"));
        historyButton.classList.add("is-active");
        $("commandConsole")?.scrollIntoView({ behavior: "smooth", block: "start" });
        log.scrollTop = log.scrollHeight;
      } catch (error) {
        const region = $("toastRegion");
        if (region) {
          const toast = document.createElement("div");
          toast.className = "toast error";
          toast.textContent = error.message || "Could not load chat history.";
          region.appendChild(toast);
          window.setTimeout(() => toast.remove(), 5000);
        }
      } finally {
        historyButton.disabled = false;
        historyButton.innerHTML = '<span aria-hidden="true">◷</span>Chat History';
      }
    });
  }

  document.querySelectorAll('.sidebar-nav a.nav-link').forEach((link) => {
    link.addEventListener("click", () => {
      document.querySelectorAll(".nav-link").forEach((item) => item.classList.remove("is-active"));
      link.classList.add("is-active");
    });
  });
})();