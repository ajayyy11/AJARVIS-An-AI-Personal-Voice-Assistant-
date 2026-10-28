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

  const assistantPanel = document.querySelector(".assistant-panel");
  const voiceLanguageSelect = $("voiceLanguage");
  const voiceOutputToggle = $("voiceOutput");
  const stopSpeakingButton = $("stopSpeakingButton");
  let recognitionInstance = null;
  let isListening = false;
  let isProcessing = false;
  let isSpeaking = false;
  let manualStop = false;
  let voiceErrorShown = false;
  let submittedTranscript = false;

  function readSetting(key) {
    try { return window.localStorage.getItem(key); }
    catch (_error) { return null; }
  }

  function writeSetting(key, value) {
    try { window.localStorage.setItem(key, value); }
    catch (_error) { /* Private browsing or storage policies may block local settings. */ }
  }

  const storedLanguage = readSetting("ajarvis.voice.language");
  if (storedLanguage && Array.from(voiceLanguageSelect.options).some((option) => option.value === storedLanguage)) {
    voiceLanguageSelect.value = storedLanguage;
  }
  voiceOutputToggle.checked = readSetting("ajarvis.voice.output") !== "false";

  function setAssistantStatus(state, label) {
    const badge = $("assistantStatus");
    if (badge) {
      badge.dataset.state = state;
      badge.textContent = label;
    }
    if (assistantPanel) {
      assistantPanel.classList.toggle("voice-listening", state === "listening");
      assistantPanel.classList.toggle("voice-speaking", state === "speaking");
      assistantPanel.classList.toggle("assistant-thinking", state === "thinking");
    }
  }

  function syncVoiceControls() {
    const micButton = $("micButton");
    if (micButton) {
      micButton.textContent = isListening ? "■" : "🎙";
      micButton.disabled = isProcessing;
      micButton.classList.toggle("is-active", isListening);
      micButton.setAttribute("aria-label", isListening ? "Stop listening" : "Start voice command");
      micButton.title = isListening ? "Stop listening" : "Start voice command";
    }
    $("sendButton").disabled = isProcessing;
    if (stopSpeakingButton) stopSpeakingButton.disabled = !isSpeaking;
  }

  function stopSpokenReply() {
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    isSpeaking = false;
    syncVoiceControls();
    if (!isProcessing && !isListening) setAssistantStatus("ready", "READY");
  }

  function speakReply(value) {
    if (!("speechSynthesis" in window) || !("SpeechSynthesisUtterance" in window)
        || !voiceOutputToggle.checked || !String(value || "").trim()) return;
    const utterance = new SpeechSynthesisUtterance(String(value).trim().slice(0, 1800));
    const language = voiceLanguageSelect.value || "en-IN";
    utterance.lang = language;
    utterance.rate = 0.98;
    utterance.pitch = 0.92;
    utterance.volume = 1;
    const voices = window.speechSynthesis.getVoices();
    const exactVoice = voices.find((voice) => voice.lang.toLowerCase() === language.toLowerCase());
    const languageVoice = voices.find((voice) => voice.lang.toLowerCase().startsWith(language.split("-")[0].toLowerCase()));
    if (exactVoice || languageVoice) utterance.voice = exactVoice || languageVoice;
    utterance.onstart = () => {
      isSpeaking = true;
      syncVoiceControls();
      setAssistantStatus("speaking", "SPEAKING");
    };
    utterance.onend = () => {
      isSpeaking = false;
      syncVoiceControls();
      if (!isProcessing && !isListening) setAssistantStatus("ready", "READY");
    };
    utterance.onerror = () => {
      isSpeaking = false;
      syncVoiceControls();
      if (!isProcessing && !isListening) setAssistantStatus("ready", "READY");
      toast("The browser could not play the spoken reply. The written answer is still available.", true, "VOICE OUTPUT");
    };
    window.speechSynthesis.cancel();
    isSpeaking = true;
    syncVoiceControls();
    setAssistantStatus("speaking", "SPEAKING");
    window.speechSynthesis.speak(utterance);
  }

  async function sendCommand(command) {
    const trimmed = String(command || "").trim();
    if (!trimmed || isProcessing) return;
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    isSpeaking = false;
    isProcessing = true;
    syncVoiceControls();
    setAssistantStatus("thinking", "ANALYZING");
    addChatMessage("user", trimmed);
    const placeholder = addChatMessage("assistant", "One moment — I'm on it…");
    let requestFailed = false;
    try {
      const result = await api("/api/assistant", {
        method: "POST",
        body: JSON.stringify({ command: trimmed })
      });
      renderAnswer(placeholder, result.response);
      speakReply(result.response);
    } catch (error) {
      requestFailed = true;
      placeholder.textContent = error.message || "AJARVIS could not answer that.";
      setAssistantStatus("error", "ATTENTION");
      toast(error.message, true, "REQUEST FAILED");
    } finally {
      isProcessing = false;
      syncVoiceControls();
      if (!isListening && !isSpeaking && !requestFailed) setAssistantStatus("ready", "READY");
      $("commandInput").focus();
      refreshHistory().catch(() => {});
      loadActivity().catch(() => {});
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

  document.querySelectorAll(".quick-command").forEach((button) => {
    button.addEventListener("click", () => sendCommand(button.dataset.command || ""));
  });

  voiceLanguageSelect.addEventListener("change", () => {
    writeSetting("ajarvis.voice.language", voiceLanguageSelect.value);
    const selected = voiceLanguageSelect.options[voiceLanguageSelect.selectedIndex];
    toast("Voice language set to " + (selected ? selected.textContent : voiceLanguageSelect.value) + ".", false, "VOICE SETTINGS");
  });
  voiceOutputToggle.addEventListener("change", () => {
    writeSetting("ajarvis.voice.output", voiceOutputToggle.checked ? "true" : "false");
    if (!voiceOutputToggle.checked) stopSpokenReply();
    toast(voiceOutputToggle.checked ? "Spoken replies enabled." : "Spoken replies muted.", false, "VOICE SETTINGS");
  });
  stopSpeakingButton.addEventListener("click", stopSpokenReply);

  $("micButton").addEventListener("click", () => {
    if (isProcessing) {
      toast("I'm still working on the previous request. One moment.", false, "AJARVIS");
      return;
    }
    if (isListening && recognitionInstance) {
      manualStop = true;
      try { recognitionInstance.stop(); } catch (_error) {}
      isListening = false;
      syncVoiceControls();
      setAssistantStatus("ready", "READY");
      toast("Listening stopped.", false, "MICROPHONE");
      return;
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setAssistantStatus("error", "VOICE UNAVAILABLE");
      toast("This browser does not support speech recognition. Try Chrome on HTTPS, or type your command instead.", true, "VOICE UNAVAILABLE");
      return;
    }

    const recognition = new SpeechRecognition();
    recognitionInstance = recognition;
    recognition.lang = voiceLanguageSelect.value || "en-IN";
    recognition.interimResults = true;
    recognition.continuous = false;
    recognition.maxAlternatives = 3;
    manualStop = false;
    voiceErrorShown = false;
    submittedTranscript = false;
    isListening = true;
    syncVoiceControls();
    setAssistantStatus("listening", "LISTENING");
    toast("Listening. Speak naturally — you can say “Hey Jarvis” first.", false, "MICROPHONE");

    recognition.onstart = () => {
      if (isListening) setAssistantStatus("listening", "LISTENING");
    };
    recognition.onresult = (event) => {
      const finalParts = [];
      const interimParts = [];
      for (let i = 0; i < event.results.length; i += 1) {
        const result = event.results[i];
        const spoken = result && result[0] ? String(result[0].transcript || "").trim() : "";
        if (!spoken) continue;
        if (result.isFinal) finalParts.push(spoken);
        else interimParts.push(spoken);
      }
      const finalText = finalParts.join(" ").trim();
      const preview = [finalText, interimParts.join(" ").trim()].filter(Boolean).join(" ").trim();
      if (preview) $("commandInput").value = preview;
      if (finalText && !submittedTranscript) {
        submittedTranscript = true;
        $("commandInput").value = finalText;
        isListening = false;
        syncVoiceControls();
        try { recognition.stop(); } catch (_error) {}
        $("chatForm").requestSubmit();
      }
    };
    recognition.onerror = (event) => {
      if (manualStop && event.error === "aborted") return;
      voiceErrorShown = true;
      isListening = false;
      const messages = {
        "not-allowed": "Microphone permission is blocked. Allow microphone access in your browser's site settings.",
        "service-not-allowed": "This browser or device policy blocked speech recognition. Try another supported browser.",
        "no-speech": "I didn't hear speech. Try again a little closer to the microphone.",
        "audio-capture": "No microphone was found. Check your microphone or headset.",
        "network": "Speech recognition could not reach the browser's speech service. Check connectivity and try again.",
        "language-not-supported": "Speech recognition isn't available for this language in this browser. Select another voice language.",
        "aborted": "Voice input was interrupted."
      };
      const message = messages[event.error] || "Voice input failed (" + String(event.error || "unknown error") + "). You can still type your request.";
      syncVoiceControls();
      setAssistantStatus("error", "MIC ISSUE");
      toast(message, true, "VOICE INPUT");
    };
    recognition.onend = () => {
      if (recognitionInstance === recognition) recognitionInstance = null;
      isListening = false;
      syncVoiceControls();
      if (!isProcessing && !isSpeaking && !voiceErrorShown) setAssistantStatus("ready", "READY");
      if (!submittedTranscript && !manualStop && !voiceErrorShown) {
        if ($("commandInput").value.trim()) {
          toast("I caught only part of that. Review the text and tap Send, or try speaking again.", true, "VOICE INPUT");
        } else {
          toast("I didn't catch anything that time. Check microphone permission and try again.", true, "VOICE INPUT");
        }
      }
    };
    try {
      recognition.start();
    } catch (_error) {
      recognitionInstance = null;
      isListening = false;
      syncVoiceControls();
      setAssistantStatus("error", "MIC ISSUE");
      toast("Could not start the microphone. Close other speech sessions and try again.", true, "VOICE INPUT");
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
  $("refreshActivity").addEventListener("click", () => loadActivity().catch(error => toast(error.message, true, "ACTIVITY")));

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
    notes.forEach((note) => {
      const item = make("article", "note-item");
      const value = typeof note === "string" ? note : ("[" + friendlyDate(note.created_at) + "] " + note.text);
      item.appendChild(make("p", "", value));
      if (note && typeof note === "object" && note.id) {
        const remove = make("button", "delete-note-button", "Delete note");
        remove.type = "button";
        remove.addEventListener("click", async () => {
          try {
            await api("/api/notes/" + note.id, { method: "DELETE" });
            await loadNotes($("noteQuery").value.trim());
            toast("Note deleted.");
          } catch (error) { toast(error.message, true, "NOTE DELETE"); }
        });
        item.appendChild(remove);
      }
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

  async function loadPreferences() {
    const result = await api("/api/preferences");
    const list = $("preferenceList");
    list.replaceChildren();
    const preferences = result.preferences || [];
    if (!preferences.length) {
      list.appendChild(make("p", "empty-state", "No saved preferences yet. Add small, useful preferences that AJARVIS should remember."));
      return;
    }
    preferences.forEach((preference) => {
      const item = make("article", "preference-item");
      const details = make("div", "preference-copy");
      details.appendChild(make("strong", "", preference.key));
      details.appendChild(make("p", "", preference.value));
      const remove = make("button", "delete-note-button", "Forget");
      remove.type = "button";
      remove.addEventListener("click", async () => {
        try {
          await api("/api/preferences/" + encodeURIComponent(preference.key), { method: "DELETE" });
          await loadPreferences();
          toast("Preference forgotten.");
        } catch (error) {
          toast(error.message, true, "PERSONAL MEMORY");
        }
      });
      item.append(details, remove);
      list.appendChild(item);
    });
  }

  $("preferenceForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const key = $("preferenceKey").value.trim();
    const value = $("preferenceValue").value.trim();
    try {
      await api("/api/preferences", {
        method: "POST",
        body: JSON.stringify({ key, value })
      });
      $("preferenceValue").value = "";
      await loadPreferences();
      toast("Personal preference saved.");
    } catch (error) {
      toast(error.message, true, "PERSONAL MEMORY");
    }
  });

  async function loadActivity() {
    const result = await api("/api/activity");
    const list = $("activityList");
    list.replaceChildren();
    const activity = result.activity || [];
    if (!activity.length) {
      list.appendChild(make("p", "empty-state", "No AI tool activity recorded yet. Ask AJARVIS to search your notes or preferences."));
      return;
    }
    activity.forEach((entry) => {
      const item = make("article", "activity-item");
      const status = make("span", "activity-status" + (entry.outcome === "success" ? " success" : " failure"),
        entry.outcome === "success" ? "✓" : "!");
      const info = make("div", "activity-copy");
      info.appendChild(make("strong", "", entry.tool_name));
      info.appendChild(make("small", "", friendlyDate(entry.created_at) + " · " + entry.duration_ms + " ms"));
      item.append(status, info);
      list.appendChild(item);
    });
  }

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
      const removeButton = make("button", "delete-document-button", "Delete document");
      removeButton.type = "button";
      removeButton.addEventListener("click", async () => {
        if (!window.confirm("Delete this saved document and its extracted text?")) return;
        try {
          await api("/api/documents/" + doc.id, { method: "DELETE" });
          await loadDocuments();
          toast("Document deleted.");
        } catch (error) { toast(error.message, true, "DOCUMENT DELETE"); }
      });
      details.appendChild(removeButton);
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

  const deleteAccountButton = $("deleteAccountButton");
  if (deleteAccountButton) {
    deleteAccountButton.addEventListener("click", async () => {
      const confirmation = window.prompt("This permanently deletes your account, notes, tasks, uploaded document text, and history. Type DELETE to continue.");
      if (confirmation !== "DELETE") return;
      const password = window.prompt("Enter your current password to confirm account deletion.");
      if (!password) return;
      deleteAccountButton.disabled = true;
      try {
        await api("/api/account/delete", {
          method: "POST",
          body: JSON.stringify({ confirmation: "DELETE", password })
        });
        window.location.assign("/register");
      } catch (error) {
        toast(error.message, true, "ACCOUNT DELETION");
        deleteAccountButton.disabled = false;
      }
    });
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
  loadPreferences().catch(error => toast(error.message, true, "PERSONAL MEMORY"));
  loadDocuments().catch(error => toast(error.message, true, "DOCUMENTS"));
  loadActivity().catch(error => toast(error.message, true, "ACTIVITY"));
  refreshHistory().catch(() => {});
  loadSystemStatus();
  claimReminders().catch(() => {});
  window.setInterval(() => claimReminders().catch(() => {}), 60000);
  window.setInterval(loadSystemStatus, 30000);
})();
