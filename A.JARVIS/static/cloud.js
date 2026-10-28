(() => {
  "use strict";

  const body = document.body;
  const csrfToken = body.dataset.csrf || "";
  const username = body.dataset.user || "User";
  const $ = (id) => document.getElementById(id);
  const toastRegion = $("toastRegion");

  function toast(message, isError = false, title = "AJARVIS") {
    const node = document.createElement("div");
    node.className = "toast" + (isError ? " error" : "");
    const heading = document.createElement("span");
    heading.className = "toast-title";
    heading.textContent = title;
    const text = document.createElement("span");
    text.textContent = String(message || "");
    node.append(heading, text);
    toastRegion.appendChild(node);
    window.setTimeout(() => node.remove(), 6500);
  }

  async function api(url, options = {}) {
    const opts = { credentials: "same-origin", ...options };
    const method = String(opts.method || "GET").toUpperCase();
    opts.headers = { ...(opts.headers || {}) };
    if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
      opts.headers["X-CSRF-Token"] = csrfToken;
    }
    if (opts.body && !(opts.body instanceof FormData) && !opts.headers["Content-Type"]) {
      opts.headers["Content-Type"] = "application/json";
    }
    let response;
    try {
      response = await fetch(url, opts);
    } catch (_error) {
      throw new Error("Could not connect to AJARVIS. Check your internet connection.");
    }
    if (response.status === 401) {
      window.location.assign("/login");
      throw new Error("Your session expired. Please sign in again.");
    }
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.error || "Request failed (" + response.status + ").");
    return result;
  }

  function make(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function renderAnswer(target, value) {
    target.replaceChildren();
    const lines = String(value || "").split("\n");
    let hasText = false;
    lines.forEach((line, index) => {
      const source = line.match(/^\[(\d+)\]\s+(.+?)\s+—\s+(https?:\/\/\S+)$/);
      if (source) {
        const link = make("a", "source-link", "[" + source[1] + "] " + source[2]);
        link.href = source[3];
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        target.appendChild(link);
        hasText = true;
      } else {
        if (index > 0 || line) target.appendChild(document.createTextNode(line));
        hasText = hasText || Boolean(line);
      }
      if (index < lines.length - 1) target.appendChild(document.createElement("br"));
    });
    if (!hasText) target.textContent = "No response text.";
  }

  function addChatMessage(role, text) {
    const log = $("chatLog");
    const row = make("div", "chat-message " + (role === "user" ? "user-message" : "assistant-message"));
    const orb = make("span", "message-orb", role === "user" ? username.slice(0, 1).toUpperCase() : "A");
    const content = make("div", "message-content");
    const label = make("small", "", role === "user" ? "YOU" : "AJARVIS");
    const message = make("p", "");
    if (role === "assistant") renderAnswer(message, text);
    else message.textContent = String(text || "");
    content.append(label, message);
    row.append(orb, content);
    log.appendChild(row);
    log.scrollTop = log.scrollHeight;
    return message;
  }

  async function sendCommand(command) {
    const trimmed = String(command || "").trim();
    if (!trimmed) return;
    addChatMessage("user", trimmed);
    const placeholder = addChatMessage("assistant", "Thinking…");
    $("sendButton").disabled = true;
    $("micButton").disabled = true;
    try {
      const result = await api("/api/assistant", {
        method: "POST",
        body: JSON.stringify({ command: trimmed })
      });
      renderAnswer(placeholder, result.response);
      if ("speechSynthesis" in window && result.response) {
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(result.response.slice(0, 1800));
        utterance.rate = 1.02;
        window.speechSynthesis.speak(utterance);
      }
    } catch (error) {
      placeholder.textContent = error.message || "AJARVIS could not answer that.";
      toast(error.message, true, "REQUEST FAILED");
    } finally {
      $("sendButton").disabled = false;
      $("micButton").disabled = false;
      $("commandInput").focus();
      refreshHistory().catch(() => {});
    }
  }

  $("chatForm").addEventListener("submit", (event) => {
    event.preventDefault();
    const input = $("commandInput");
    const command = input.value;
    input.value = "";
    sendCommand(command);
  });
  $("commandInput").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      $("chatForm").requestSubmit();
    }
  });

  $("micButton").addEventListener("click", () => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      toast("Voice input is not available in this browser. You can still type your request.", true, "VOICE UNAVAILABLE");
      return;
    }
    const recognition = new SpeechRecognition();
    recognition.lang = navigator.language || "en-US";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    $("micButton").disabled = true;
    toast("Listening. Speak your request now.", false, "MICROPHONE");
    recognition.onresult = (event) => {
      const transcript = event.results && event.results[0] && event.results[0][0]
        ? event.results[0][0].transcript : "";
      $("commandInput").value = transcript;
      $("chatForm").requestSubmit();
    };
    recognition.onerror = () => toast("Voice input failed or microphone access was denied.", true, "VOICE INPUT");
    recognition.onend = () => { $("micButton").disabled = false; };
    try { recognition.start(); } catch (_error) {
      $("micButton").disabled = false;
      toast("Could not start voice input.", true, "VOICE INPUT");
    }
  });

  async function refreshHistory() {
    const result = await api("/api/history");
    const rows = result.history || [];
    if (!rows.length) return;
    const log = $("chatLog");
    if (log.dataset.historyLoaded === "true") return;
    log.dataset.historyLoaded = "true";
    log.replaceChildren();
    rows.slice().reverse().forEach((entry) => {
      addChatMessage("user", entry.command || "");
      addChatMessage("assistant", entry.response || "");
    });
    if (!rows.length) addChatMessage("assistant", "Hello " + username + ". How can I help?");
  }

  function friendlyDate(value) {
    if (!value) return "No reminder set";
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString();
  }

  async function loadTasks() {
    const result = await api("/api/tasks");
    const list = $("taskList");
    list.replaceChildren();
    const tasks = result.tasks || [];
    if (!tasks.length) {
      list.appendChild(make("p", "empty-state", "No tasks yet. Add one above to start organizing your day."));
      return;
    }
    tasks.forEach((task) => {
      const row = make("div", "task-item" + (task.done ? " done" : ""));
      const check = make("input", "task-check");
      check.type = "checkbox";
      check.checked = Boolean(task.done);
      check.setAttribute("aria-label", "Mark " + task.title + " as " + (task.done ? "not done" : "done"));
      check.addEventListener("change", async () => {
        try {
          await api("/api/tasks/" + task.id, { method: "PATCH", body: JSON.stringify({ done: check.checked }) });
          await loadTasks();
        } catch (error) {
          check.checked = !check.checked;
          toast(error.message, true, "TASK UPDATE");
        }
      });
      const details = make("div", "task-copy");
      details.appendChild(make("strong", "", task.title));
      if (task.details) details.appendChild(make("p", "", task.details));
      if (task.due_at) details.appendChild(make("small", "", "◷ " + friendlyDate(task.due_at) + (task.reminder_notified ? " · notified" : "")));
      const remove = make("button", "delete-task", "×");
      remove.type = "button";
      remove.title = "Delete task";
      remove.setAttribute("aria-label", "Delete " + task.title);
      remove.addEventListener("click", async () => {
        try {
          await api("/api/tasks/" + task.id, { method: "DELETE" });
          await loadTasks();
          toast("Task deleted.");
        } catch (error) { toast(error.message, true, "TASK DELETE"); }
      });
      row.append(check, details, remove);
      list.appendChild(row);
    });
  }

  $("taskForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const title = $("taskTitle").value.trim();
    const details = $("taskDetails").value.trim();
    const localDue = $("taskDue").value;
    let dueAt = null;
    if (localDue) {
      const parsed = new Date(localDue);
      if (Number.isNaN(parsed.getTime())) {
        toast("Choose a valid reminder time.", true, "INVALID TIME");
        return;
      }
      dueAt = parsed.toISOString();
    }
    try {
      await api("/api/tasks", {
        method: "POST",
        body: JSON.stringify({ title, details, due_at: dueAt })
      });
      $("taskForm").reset();
      await loadTasks();
      toast("Task saved.");
    } catch (error) { toast(error.message, true, "TASK SAVE"); }
  });
  $("refreshTasks").addEventListener("click", () => loadTasks().catch(error => toast(error.message, true)));

  async function claimReminders() {
    const result = await api("/api/reminders/claim", {
      method: "POST",
      body: JSON.stringify({})
    });
    (result.reminders || []).forEach((item) => {
      const message = "Reminder: " + item.title;
      toast(message, false, "TASK DUE");
      if ("Notification" in window && Notification.permission === "granted") {
        try { new Notification("AJARVIS reminder", { body: message }); } catch (_error) {}
      }
    });
    if ((result.reminders || []).length) loadTasks().catch(() => {});
  }

  $("enableNotifications").addEventListener("click", async () => {
    if (!("Notification" in window)) {
      toast("This browser does not support desktop notifications. In-page reminders still work.", true, "NOTIFICATIONS");
      return;
    }
    try {
      const permission = await Notification.requestPermission();
      toast(permission === "granted" ? "Browser notifications enabled." : "Notifications were not enabled.", permission !== "granted", "NOTIFICATIONS");
    } catch (_error) {
      toast("Could not enable browser notifications.", true, "NOTIFICATIONS");
    }
  });

  async function loadNotes(query = "") {
    const url = query ? "/api/notes?q=" + encodeURIComponent(query) : "/api/notes";
    const result = await api(url);
    const list = $("noteList");
    list.replaceChildren();
    const notes = result.notes || [];
    if (!notes.length) {
      list.appendChild(make("p", "empty-state", query ? "No matching notes found." : "No saved notes yet."));
      return;
    }
    notes.slice().reverse().forEach((line) => {
      const item = make("article", "note-item");
      item.appendChild(make("p", "", line));
      list.appendChild(item);
    });
  }

  $("noteForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = $("noteText").value.trim();
    try {
      await api("/api/notes", { method: "POST", body: JSON.stringify({ text }) });
      $("noteText").value = "";
      await loadNotes();
      toast("Note saved securely to your account.");
    } catch (error) { toast(error.message, true, "NOTE SAVE"); }
  });
  $("noteSearchForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try { await loadNotes($("noteQuery").value.trim()); }
    catch (error) { toast(error.message, true, "NOTE SEARCH"); }
  });

  async function loadDocuments() {
    const result = await api("/api/documents");
    const list = $("documentList");
    list.replaceChildren();
    const documents = result.documents || [];
    if (!documents.length) {
      list.appendChild(make("p", "empty-state", "Upload a document to ask questions about its extracted text."));
      return;
    }
    documents.forEach((doc) => {
      const item = make("article", "document-item");
      item.appendChild(make("span", "document-icon", "▧"));
      const details = make("div", "document-copy");
      details.appendChild(make("strong", "", doc.filename));
      details.appendChild(make("small", "", (doc.page_count ? String(doc.page_count) + " pages/sheets · " : "") + friendlyDate(doc.created_at)));
      const questionForm = make("form", "document-question");
      const question = make("input", "");
      question.type = "text";
      question.maxLength = 1500;
      question.placeholder = "Ask a question about this document";
      question.required = true;
      const askButton = make("button", "secondary-button", "Ask");
      askButton.type = "submit";
      questionForm.append(question, askButton);
      questionForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        askButton.disabled = true;
        const answerBox = make("p", "document-answer", "Reading document…");
        details.appendChild(answerBox);
        try {
          const answer = await api("/api/documents/" + doc.id + "/ask", {
            method: "POST",
            body: JSON.stringify({ question: question.value.trim() })
          });
          renderAnswer(answerBox, answer.answer);
        } catch (error) {
          answerBox.textContent = error.message;
          toast(error.message, true, "DOCUMENT Q&A");
        } finally { askButton.disabled = false; }
      });
      details.appendChild(questionForm);
      item.appendChild(details);
      list.appendChild(item);
    });
  }

  $("documentForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const fileInput = $("documentFile");
    const file = fileInput.files && fileInput.files[0];
    if (!file) {
      toast("Choose a document first.", true, "DOCUMENT UPLOAD");
      return;
    }
    if (file.size > 8 * 1024 * 1024) {
      toast("Document uploads are limited to 8 MB.", true, "DOCUMENT TOO LARGE");
      return;
    }
    const uploadButton = $("uploadButton");
    uploadButton.disabled = true;
    uploadButton.textContent = "Extracting and analysing…";
    $("documentResult").textContent = "";
    const formData = new FormData();
    formData.append("file", file);
    try {
      const result = await api("/api/documents", { method: "POST", body: formData });
      $("documentResult").textContent = result.summary || "Document saved.";
      if (result.page_count) $("documentResult").textContent += "\nPages/sheets: " + result.page_count;
      fileInput.value = "";
      await loadDocuments();
      toast("Document saved to your account.");
    } catch (error) {
      $("documentResult").textContent = error.message;
      toast(error.message, true, "DOCUMENT UPLOAD");
    } finally {
      uploadButton.disabled = false;
      uploadButton.textContent = "Upload & analyse";
    }
  });

  async function loadSystemStatus() {
    try {
      const result = await api("/api/system");
      $("serverStatus").textContent = result.available === false ? "Limited metrics" : "Operational";
      if (result.cpu_percent !== undefined) {
        $("serverStats").textContent = "Cloud host · CPU " + result.cpu_percent + "% · RAM " + result.memory_percent + "%";
      } else {
        $("serverStats").textContent = "Metrics unavailable";
      }
    } catch (_error) {
      $("serverStatus").textContent = "Metrics unavailable";
    }
  }

  $("logoutButton").addEventListener("click", async () => {
    $("logoutButton").disabled = true;
    try {
      await api("/api/auth/logout", { method: "POST", body: JSON.stringify({}) });
      window.location.assign("/login");
    } catch (error) {
      toast(error.message, true, "SIGN OUT");
      $("logoutButton").disabled = false;
    }
  });

  loadTasks().catch(error => toast(error.message, true, "TASKS"));
  loadNotes().catch(error => toast(error.message, true, "NOTES"));
  loadDocuments().catch(error => toast(error.message, true, "DOCUMENTS"));
  refreshHistory().catch(() => {});
  loadSystemStatus();
  claimReminders().catch(() => {});
  window.setInterval(() => claimReminders().catch(() => {}), 60000);
  window.setInterval(loadSystemStatus, 30000);
})();
