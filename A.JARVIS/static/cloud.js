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

  const historyCursorKey = "ajarvis.cloud.context_after_id:" + username.toLowerCase();
  function readContextAfterId() {
    const candidates = [body.dataset.contextAfterId];
    try { candidates.push(window.localStorage.getItem(historyCursorKey)); } catch (_error) {}
    try { candidates.push(window.sessionStorage.getItem(historyCursorKey)); } catch (_error) {}
    for (const raw of candidates) {
      if (raw === null || raw === undefined || raw === "") continue;
      const value = Number(raw);
      if (Number.isSafeInteger(value) && value >= 0) return value;
    }
    return null;
  }

  function historyEndpoint() {
    const cursor = readContextAfterId();
    return cursor === null ? "/api/history" : "/api/history?after_id=" + encodeURIComponent(String(cursor));
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
    if (stopSpeakingButton) {
      stopSpeakingButton.disabled = !isSpeaking;
      stopSpeakingButton.hidden = !isSpeaking;
    }
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
      const payload = { command: trimmed };
      const contextAfterId = readContextAfterId();
      if (contextAfterId !== null) payload.context_after_id = contextAfterId;
      const result = await api("/api/assistant", {
        method: "POST",
        body: JSON.stringify(payload)
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
      if (body.dataset.page === "history") refreshHistory().catch(() => {});
      if (body.dataset.page === "activity") loadActivity().catch(() => {});
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
    if (isSpeaking) stopSpokenReply();
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
    recognition.continuous = true;
    recognition.maxAlternatives = 1;
    manualStop = false;
    voiceErrorShown = false;
    submittedTranscript = false;
    let waitingForCommand = false;
    isListening = true;
    syncVoiceControls();
    setAssistantStatus("listening", "LISTENING");
    toast("Listening. Speak naturally — you can say “Hey Jarvis” first.", false, "MICROPHONE");

    recognition.onstart = () => {
      if (isListening) setAssistantStatus("listening", "LISTENING");
    };
    let capturedFinalTranscript = "";
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
      if (finalText) capturedFinalTranscript = finalText;
      const preview = [capturedFinalTranscript, interimParts.join(" ").trim()].filter(Boolean).join(" ").trim();
      if (preview) $("commandInput").value = preview;
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

      if (!isProcessing && !isSpeaking && !voiceErrorShown) {
        setAssistantStatus("ready", "READY");
      }

      if (submittedTranscript || manualStop || voiceErrorShown) return;

      const rawTranscript = capturedFinalTranscript || $("commandInput").value.trim();
      const cleanedTranscript = rawTranscript
        .replace(/^\\s*(?:(?:hey|hi|hello|ok|okay)\\s+)?jarvis[,.!?]?\\s*/i, "")
        .trim();
      const hasWakeWord = /(?:^|\\s)(?:hey|hi|hello|ok|okay)?\\s*jarvis(?:$|[,.!?\\s])/i.test(rawTranscript);
      const command = waitingForCommand ? rawTranscript.trim() : cleanedTranscript;

      if (!command && hasWakeWord && !waitingForCommand) {
        waitingForCommand = true;
        capturedFinalTranscript = "";
        $("commandInput").value = "";
        toast("Yes? I'm listening. Please say your command now.", false, "AJARVIS");
        if (!manualStop && !voiceErrorShown) {
          try {
            recognitionInstance = recognition;
            isListening = true;
            recognition.start();
            syncVoiceControls();
            setAssistantStatus("listening", "LISTENING");
            return;
          } catch (_error) {
            recognitionInstance = null;
            isListening = false;
          }
        }
      }

      if (!command) {
        $("commandInput").value = "";
        toast(
          rawTranscript
            ? "I heard the wake word, but not the command. Tap the microphone and try again."
            : "I didn't catch anything. Check microphone permission and try again.",
          true,
          "VOICE INPUT"
        );
        return;
      }

      submittedTranscript = true;
      $("commandInput").value = command;
      $("chatForm").requestSubmit();
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

  let historyBeforeId = null;
  let historyLoading = false;

  async function refreshHistory(reset = true) {
    if (body.dataset.page !== "history" || historyLoading) return;
    const list = $("historyList");
    const loadOlderButton = $("loadOlderHistory");
    if (!list) return;
    if (!reset && historyBeforeId === null) return;

    historyLoading = true;
    if (loadOlderButton) {
      loadOlderButton.disabled = true;
      loadOlderButton.textContent = "Loading…";
    }
    try {
      const endpoint = reset || historyBeforeId === null
        ? "/api/history"
        : "/api/history?before_id=" + encodeURIComponent(String(historyBeforeId));
      const result = await api(endpoint);
      const rows = Array.isArray(result.history) ? result.history : [];
      if (reset) list.replaceChildren();

      if (!rows.length && reset) {
        list.appendChild(make("p", "empty-state", "No saved conversations yet. Start a new chat with AJARVIS."));
      } else {
        const firstIndex = list.querySelectorAll(".history-item").length;
        rows.forEach((entry, index) => {
          const card = make("article", "history-item");
          const heading = make("div", "history-item-heading");
          heading.appendChild(make("strong", "", "Saved exchange " + (firstIndex + index + 1)));
          const question = make("p", "history-question", entry.command || "Question not available");
          const answer = make("p", "history-answer", entry.response || "Response not available");
          card.append(heading, question, answer);
          list.appendChild(card);
        });
      }

      historyBeforeId = result.has_more && Number.isSafeInteger(result.next_before_id)
        ? result.next_before_id
        : null;
      if (loadOlderButton) {
        loadOlderButton.hidden = historyBeforeId === null;
        loadOlderButton.disabled = historyBeforeId === null;
        loadOlderButton.textContent = "Load older exchanges";
      }
    } catch (error) {
      if (loadOlderButton) loadOlderButton.textContent = "Retry loading older exchanges";
      toast(error.message, true, "CHAT HISTORY");
    } finally {
      historyLoading = false;
      if (loadOlderButton && historyBeforeId !== null) loadOlderButton.disabled = false;
    }
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

  const visualFileInput = $("visualFile");
  const visualCameraButton = $("visualCameraButton");
  const visualScreenButton = $("visualScreenButton");
  const visualCaptureButton = $("visualCaptureButton");
  const visualCancelCapture = $("visualCancelCapture");
  const visualClearButton = $("visualClearButton");
  const visualAnalyzeButton = $("visualAnalyzeButton");
  const visualCameraPreview = $("visualCameraPreview");
  const visualImagePreview = $("visualImagePreview");
  const visualSelection = $("visualSelection");
  const visualPrompt = $("visualPrompt");
  const visualResult = $("visualResult");
  const visualCanvas = document.createElement("canvas");
  let visualFile = null;
  let visualPreviewUrl = null;
  let visualCameraStream = null;

  function stopVisualCamera() {
    if (visualCameraStream) {
      visualCameraStream.getTracks().forEach((track) => track.stop());
      visualCameraStream = null;
    }
    visualCameraPreview.pause();
    visualCameraPreview.srcObject = null;
    visualCameraPreview.hidden = true;
    visualCaptureButton.hidden = true;
    visualCancelCapture.hidden = true;
    visualCameraButton.textContent = "Open camera";
  }

  function clearVisualPreviewUrl() {
    if (visualPreviewUrl) {
      URL.revokeObjectURL(visualPreviewUrl);
      visualPreviewUrl = null;
    }
  }

  function setVisualFile(file, sourceLabel) {
    clearVisualPreviewUrl();
    visualFile = file || null;
    visualImagePreview.hidden = true;
    visualImagePreview.removeAttribute("src");
    if (visualFile && visualFile.type.startsWith("image/")) {
      visualPreviewUrl = URL.createObjectURL(visualFile);
      visualImagePreview.src = visualPreviewUrl;
      visualImagePreview.hidden = false;
    }
    visualAnalyzeButton.disabled = !visualFile;
    visualClearButton.hidden = !visualFile;
    visualSelection.textContent = visualFile
      ? sourceLabel + ": " + visualFile.name + " · " + (visualFile.size / 1024).toFixed(0) + " KB · not uploaded yet"
      : "No visual selected. Camera and screen access start only when you press their buttons.";
    visualResult.textContent = "";
  }

  function captureVisualFrame(video, namePrefix) {
    if (!video.videoWidth || !video.videoHeight) {
      throw new Error("The selected camera or screen has no video frame yet. Try again.");
    }
    const scale = Math.min(1, 1600 / Math.max(video.videoWidth, video.videoHeight));
    visualCanvas.width = Math.max(1, Math.round(video.videoWidth * scale));
    visualCanvas.height = Math.max(1, Math.round(video.videoHeight * scale));
    const context = visualCanvas.getContext("2d", { alpha: false });
    if (!context) throw new Error("This browser cannot capture a visual frame.");
    context.drawImage(video, 0, 0, visualCanvas.width, visualCanvas.height);
    return new Promise((resolve, reject) => {
      visualCanvas.toBlob((blob) => {
        if (!blob) {
          reject(new Error("Could not create the visual snapshot."));
          return;
        }
        resolve(new File([blob], namePrefix + "-" + Date.now() + ".jpg", { type: "image/jpeg" }));
      }, "image/jpeg", 0.86);
    });
  }

  visualFileInput.addEventListener("change", () => {
    stopVisualCamera();
    const file = visualFileInput.files && visualFileInput.files[0];
    setVisualFile(file || null, "Selected file");
  });

  visualCameraButton.addEventListener("click", async () => {
    if (visualCameraStream) {
      stopVisualCamera();
      return;
    }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      toast("Camera capture is not supported in this browser. Choose an image instead.", true, "CAMERA UNAVAILABLE");
      return;
    }
    try {
      visualCameraStream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 }, height: { ideal: 720 } }
      });
      visualCameraPreview.srcObject = visualCameraStream;
      visualCameraPreview.hidden = false;
      await visualCameraPreview.play();
      visualCaptureButton.hidden = false;
      visualCancelCapture.hidden = false;
      visualCameraButton.textContent = "Camera active";
      visualSelection.textContent = "Camera preview is local. Press Capture photo to select one frame.";
    } catch (error) {
      stopVisualCamera();
      toast(error.message || "Camera permission was not granted.", true, "CAMERA ACCESS");
    }
  });

  visualCaptureButton.addEventListener("click", async () => {
    try {
      const snapshot = await captureVisualFrame(visualCameraPreview, "ajarvis-camera");
      stopVisualCamera();
      setVisualFile(snapshot, "Camera snapshot");
      toast("One camera frame captured locally. It has not been uploaded.", false, "VISUAL CAPTURE");
    } catch (error) {
      stopVisualCamera();
      toast(error.message, true, "CAMERA CAPTURE");
    }
  });

  visualCancelCapture.addEventListener("click", stopVisualCamera);

  visualScreenButton.addEventListener("click", async () => {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) {
      toast("Screen capture is not supported in this browser. Choose an image instead.", true, "SCREEN CAPTURE UNAVAILABLE");
      return;
    }
    stopVisualCamera();
    let stream = null;
    try {
      // The browser opens its native picker. Only one frame is captured and the stream is stopped.
      stream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false });
      visualCameraPreview.srcObject = stream;
      visualCameraPreview.hidden = false;
      await visualCameraPreview.play();
      await new Promise((resolve) => {
        let settled = false;
        const finish = () => { if (!settled) { settled = true; resolve(); } };
        if (typeof visualCameraPreview.requestVideoFrameCallback === "function") {
          visualCameraPreview.requestVideoFrameCallback(finish);
        }
        window.setTimeout(finish, 500);
      });
      const snapshot = await captureVisualFrame(visualCameraPreview, "ajarvis-screen");
      stream.getTracks().forEach((track) => track.stop());
      stream = null;
      visualCameraPreview.pause();
      visualCameraPreview.srcObject = null;
      visualCameraPreview.hidden = true;
      setVisualFile(snapshot, "Screen snapshot");
      toast("One screen frame captured. Screen sharing has stopped.", false, "VISUAL CAPTURE");
    } catch (error) {
      toast(error.message || "Screen capture was cancelled or unavailable.", true, "SCREEN CAPTURE");
    } finally {
      if (stream) stream.getTracks().forEach((track) => track.stop());
      if (!visualCameraStream) {
        visualCameraPreview.pause();
        visualCameraPreview.srcObject = null;
        visualCameraPreview.hidden = true;
      }
    }
  });

  visualClearButton.addEventListener("click", () => {
    stopVisualCamera();
    clearVisualPreviewUrl();
    visualFile = null;
    visualFileInput.value = "";
    setVisualFile(null, "");
  });

  visualAnalyzeButton.addEventListener("click", async () => {
    if (!visualFile) {
      toast("Choose an image or PDF first.", true, "VISUAL INTELLIGENCE");
      return;
    }
    const isPdf = visualFile.name.toLowerCase().endsWith(".pdf");
    const sizeLimit = isPdf ? 8 * 1024 * 1024 : 5 * 1024 * 1024;
    if (visualFile.size > sizeLimit) {
      toast(isPdf ? "PDF uploads are limited to 8 MB." : "Image uploads are limited to 5 MB.", true, "FILE TOO LARGE");
      return;
    }
    const payload = new FormData();
    payload.append("file", visualFile);
    payload.append("prompt", visualPrompt.value.trim());
    visualAnalyzeButton.disabled = true;
    visualAnalyzeButton.textContent = "Analyzing…";
    visualResult.textContent = "AJARVIS is examining the selected visual input. Media is processed for this request and is not saved.";
    try {
      const result = await api("/api/visual/analyze", { method: "POST", body: payload });
      visualResult.textContent = result.answer || "No visual answer was returned.";
      if (result.page_count) visualResult.textContent += "\nPDF pages: " + result.page_count;
      visualSelection.textContent = result.filename + " · " + result.mime_type + " · processed transiently";
      toast("Visual analysis completed. The media was not saved.", false, "VISUAL INTELLIGENCE");
    } catch (error) {
      visualResult.textContent = error.message;
      toast(error.message, true, "VISUAL ANALYSIS");
    } finally {
      visualAnalyzeButton.disabled = !visualFile;
      visualAnalyzeButton.textContent = "Analyze visual input";
    }
  });

  window.addEventListener("pagehide", () => {
    stopVisualCamera();
    clearVisualPreviewUrl();
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

  const activePage = body.dataset.page || "dashboard";
  if (activePage === "tasks") loadTasks().catch(error => toast(error.message, true, "TASKS"));
  if (activePage === "notes") loadNotes().catch(error => toast(error.message, true, "NOTES"));
  if (activePage === "memory") loadPreferences().catch(error => toast(error.message, true, "PERSONAL MEMORY"));
  if (activePage === "documents") loadDocuments().catch(error => toast(error.message, true, "DOCUMENTS"));
  if (activePage === "activity") loadActivity().catch(error => toast(error.message, true, "ACTIVITY"));
  if (activePage === "history") {
    const loadOlderButton = $("loadOlderHistory");
    if (loadOlderButton) loadOlderButton.addEventListener("click", () => refreshHistory(false));
    refreshHistory().catch(error => toast(error.message, true, "CHAT HISTORY"));
  }
  loadSystemStatus();
  claimReminders().catch(() => {});
  window.setInterval(() => claimReminders().catch(() => {}), 60000);
  window.setInterval(loadSystemStatus, 30000);
})();
