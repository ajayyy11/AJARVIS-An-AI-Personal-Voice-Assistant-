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
  const sidebar = $("workspaceSidebar");
  const sidebarToggle = $("mobileNavToggle");
  const sidebarBackdrop = $("sidebarBackdrop");

  function setSidebarOpen(open) {
    if (!sidebar || !sidebarToggle || !sidebarBackdrop) return;
    sidebar.classList.toggle("is-open", open);
    sidebarBackdrop.hidden = !open;
    sidebarToggle.setAttribute("aria-expanded", String(open));
    sidebarToggle.setAttribute("aria-label", open ? "Close feature navigation" : "Open feature navigation");
    document.body.classList.toggle("sidebar-open", open);
  }

  if (sidebarToggle) {
    sidebarToggle.addEventListener("click", () => {
      setSidebarOpen(sidebarToggle.getAttribute("aria-expanded") !== "true");
    });
  }
  if (sidebarBackdrop) sidebarBackdrop.addEventListener("click", () => setSidebarOpen(false));
  document.querySelectorAll(".sidebar-nav .nav-link").forEach((item) => {
    item.addEventListener("click", () => setSidebarOpen(false));
  });

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
      if (event.key === "Escape") {
        closeStatusPanel();
        setSidebarOpen(false);
      }
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

  // Feature links now navigate to dedicated pages; only close the mobile drawer here.
  document.querySelectorAll(".sidebar-nav a.nav-link").forEach((link) => {
    link.addEventListener("click", () => setSidebarOpen(false));
  });

})();