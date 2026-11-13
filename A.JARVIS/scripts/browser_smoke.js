"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { JSDOM, VirtualConsole } = require("jsdom");

const fixtureDir = process.argv[2];
if (!fixtureDir) throw new Error("Pass the rendered fixture directory.");

const routes = [
  ["dashboard", "/dashboard"],
  ["history", "/history"],
  ["tasks", "/tasks"],
  ["notes", "/notes"],
  ["memory", "/memory"],
  ["activity", "/activity"],
  ["visual", "/visual"],
  ["documents", "/documents"],
  ["account", "/account"],
  ["settings", "/settings"],
];

const wait = (ms = 20) => new Promise((resolve) => setTimeout(resolve, ms));
const failures = [];
const successes = [];
const assert = (condition, message) => {
  if (!condition) throw new Error(message);
};

function jsonResponse(payload, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => "application/json" },
    json: async () => payload,
    text: async () => JSON.stringify(payload),
  };
}

async function mountPage(page, options = {}) {
  const html = fs.readFileSync(path.join(fixtureDir, page + ".html"), "utf8");
  const virtualConsole = new VirtualConsole();
  const runtimeErrors = [];
  virtualConsole.on("jsdomError", (error) => runtimeErrors.push(error.message));
  const dom = new JSDOM(html, {
    url: "https://ajarvis.test/" + (page === "dashboard" ? "dashboard" : page),
    runScripts: "outside-only",
    pretendToBeVisual: true,
    virtualConsole,
  });
  const { window } = dom;
  const calls = [];
  const state = {
    tasks: [],
    notes: [],
    preferences: [],
    documents: [],
    activity: [],
    failInitialHistory: Boolean(options.failInitialHistory),
    initialHistoryFailureUsed: false,
    // /api/history returns records newest-first (ORDER BY id DESC).
    history: [
      { command: "Newest saved question", response: "Newest saved answer" },
      { command: "Older saved question", response: "Older saved answer" },
    ],
  };

  window.setInterval = () => 1;
  window.clearInterval = () => {};
  window.scrollTo = () => {};
  window.HTMLElement.prototype.scrollIntoView = function scrollIntoView() {};
  window.URL.createObjectURL = () => "blob:ajarvis-qa-preview";
  window.URL.revokeObjectURL = () => {};
  window.SpeechSynthesisUtterance = class SpeechSynthesisUtterance {
    constructor(text) { this.text = text; }
  };
  window.speechSynthesis = {
    cancel() {},
    getVoices: () => [{ lang: "en-IN" }],
    speak(utterance) { window.lastUtterance = utterance; },
  };
  window.matchMedia = () => ({ matches: false, addListener() {}, removeListener() {} });

  class MockRecognition {
    constructor() { window.lastRecognition = this; }
    start() { if (this.onstart) this.onstart(); }
    stop() { if (this.onend) this.onend(); }
  }
  window.SpeechRecognition = MockRecognition;

  window.fetch = async (url, options = {}) => {
    const method = String(options.method || "GET").toUpperCase();
    let body = options.body;
    if (typeof body === "string") {
      try { body = JSON.parse(body); } catch (_error) {}
    }
    calls.push({ url: String(url), method, body, headers: options.headers || {} });

    if (url === "/api/system") return jsonResponse({ cpu_percent: 12, memory_percent: 34 });
    if (url === "/api/reminders/claim") return jsonResponse({ reminders: [] });
    if (url === "/api/history") {
      if (state.failInitialHistory && !state.initialHistoryFailureUsed) {
        state.initialHistoryFailureUsed = true;
        return jsonResponse({ error: "History temporarily unavailable." }, 503);
      }
      return jsonResponse({ history: state.history, latest_id: 42, has_more: true, next_before_id: 40 });
    }
    if (url === "/api/history?before_id=40") {
      return jsonResponse({
        history: [{ id: 39, command: "Much older saved question", response: "Much older saved answer" }],
        latest_id: 42,
        has_more: false,
        next_before_id: null,
      });
    }
    if (url === "/api/tasks" && method === "GET") return jsonResponse({ tasks: state.tasks });
    if (url === "/api/tasks" && method === "POST") {
      const task = { id: state.tasks.length + 1, title: body.title, details: body.details || "", done: false };
      state.tasks.push(task);
      return jsonResponse({ task }, 201);
    }
    if (url === "/api/notes" && method === "GET") return jsonResponse({ notes: state.notes });
    if (url === "/api/notes" && method === "POST") {
      state.notes.push({ id: state.notes.length + 1, text: body.text, created_at: "2026-11-06T00:00:00Z" });
      return jsonResponse({ note: state.notes[state.notes.length - 1] }, 201);
    }
    if (url === "/api/preferences" && method === "GET") return jsonResponse({ preferences: state.preferences });
    if (url === "/api/preferences" && method === "POST") {
      state.preferences.push({ key: body.key, value: body.value });
      return jsonResponse({ preference: state.preferences[state.preferences.length - 1] }, 201);
    }
    if (url === "/api/documents" && method === "GET") return jsonResponse({ documents: state.documents });
    if (url === "/api/documents" && method === "POST") {
      state.documents.push({ id: state.documents.length + 1, filename: "qa.txt", created_at: "2026-11-06T00:00:00Z" });
      return jsonResponse({ summary: "Document accepted for QA.", filename: "qa.txt" }, 201);
    }
    if (url === "/api/visual/analyze" && method === "POST") {
      return jsonResponse({ answer: "A QA sample image.", filename: "qa.png", mime_type: "image/png" });
    }
    if (url === "/api/activity") return jsonResponse({ activity: state.activity });
    if (url === "/api/assistant") return jsonResponse({ response: "It is 12:00 UTC." });
    if (url === "/api/auth/logout") return jsonResponse({ ok: true });
    if (url === "/api/reminders/claim") return jsonResponse({ reminders: [] });
    if (url === "/api/tasks/1" && method === "PATCH") return jsonResponse({ task: state.tasks[0] });
    return jsonResponse({ error: "Unexpected smoke-test API request: " + method + " " + url }, 404);
  };

  window.eval(fs.readFileSync(path.join(__dirname, "..", "static", "cloud.js"), "utf8"));
  window.eval(fs.readFileSync(path.join(__dirname, "..", "static", "interface.js"), "utf8"));
  await wait(30);

  return { dom, window, document: window.document, calls, state, runtimeErrors };
}

async function runPageSmoke(page, route) {
  const app = await mountPage(page);
  try {
    const { document, calls, runtimeErrors } = app;
    assert(document.body.dataset.page === page, page + ": wrong active page marker");
    assert(document.querySelector(".sidebar"), page + ": sidebar is missing");
    assert(document.querySelector('.sidebar-nav a[aria-current="page"]'), page + ": active navigation link is missing");
    assert(document.querySelector('.sidebar-nav a[href="' + route + '"]'), page + ": navigation target is missing");
    assert(!runtimeErrors.length, page + ": JavaScript runtime errors: " + runtimeErrors.join("; "));

    const oldHistoryInjected = document.querySelector("#chatLog").textContent.includes("Older saved question");
    assert(!oldHistoryInjected, page + ": saved history leaked into the chat transcript");

    const startupCalls = calls.map((x) => x.url);
    const endpointByPage = {
      dashboard: null,
      history: "/api/history",
      tasks: "/api/tasks",
      notes: "/api/notes",
      memory: "/api/preferences",
      activity: "/api/activity",
      visual: null,
      documents: "/api/documents",
      account: null,
      settings: null,
    };
    const expected = endpointByPage[page];
    if (expected) assert(startupCalls.includes(expected), page + ": feature data did not load");
    if (page !== "history") {
      assert(!startupCalls.includes("/api/history"), page + ": history API loaded outside History page");
    }

    if (page === "history") {
      assert(document.querySelector("#historyList").textContent.includes("Newest saved question"), "history: newest exchange is missing");
      assert(document.querySelector("#historyList").textContent.indexOf("Newest saved question") < document.querySelector("#historyList").textContent.indexOf("Older saved question"), "history: newest exchange must appear first");
      const olderButton = document.querySelector("#loadOlderHistory");
      assert(olderButton && !olderButton.hidden, "history: load-older control should appear when another page exists");
      olderButton.click();
      await wait(30);
      assert(document.querySelector("#historyList").textContent.includes("Much older saved question"), "history: older page did not append");
      assert(olderButton.hidden, "history: load-older control should hide after the final page");
    }
    successes.push("page rendering and startup: " + page);
  } finally {
    app.dom.window.close();
  }
}

async function testChatAndVoice() {
  const app = await mountPage("dashboard");
  try {
    const { window, document, calls } = app;
    const input = document.querySelector("#commandInput");
    input.value = "What time is it?";
    document.querySelector("#chatForm").dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
    await wait(35);
    let assistantCall = calls.find((call) => call.url === "/api/assistant");
    assert(assistantCall, "text chat did not call the assistant endpoint");
    assert(assistantCall.body.command === "What time is it?", "text chat sent an incorrect command");
    assert(assistantCall.body.context_after_id === 42, "new chat did not send the server-provided history boundary");

    document.querySelector("#commandInput").value = "";
    document.querySelector("#micButton").click();
    const recognition = window.lastRecognition;
    assert(recognition, "microphone button did not start speech recognition");
    recognition.onresult({
      results: [
        Object.assign([{ transcript: "What is the current time?" }], { isFinal: true }),
      ],
    });
    recognition.onend();
    await wait(35);
    assistantCall = calls.filter((call) => call.url === "/api/assistant").at(-1);
    assert(assistantCall && assistantCall.body.command === "What is the current time?", "voice transcript was not submitted exactly once");
    assert(document.querySelector("#chatLog").textContent.includes("It is 12:00 UTC."), "assistant reply was not rendered");

    document.querySelector("#commandInput").value = "";
    document.querySelector("#micButton").click();
    const manualRecognition = window.lastRecognition;
    manualRecognition.onresult({
      results: [
        Object.assign([{ transcript: "Manual stop should send this command" }], { isFinal: true }),
      ],
    });
    document.querySelector("#micButton").click();
    await wait(35);
    assistantCall = calls.filter((call) => call.url === "/api/assistant").at(-1);
    assert(
      assistantCall && assistantCall.body.command === "Manual stop should send this command",
      "manual microphone stop discarded the final transcript"
    );
    successes.push("text chat, fresh context boundary, automatic voice end, manual voice stop and reply rendering");
  } finally {
    app.dom.window.close();
  }
}

async function testBusyChatPreservesDraft() {
  const app = await mountPage("dashboard");
  try {
    const { window, document } = app;
    const input = document.querySelector("#commandInput");
    const originalFetch = window.fetch;
    const commands = [];
    let finishFirstRequest;
    window.fetch = async (url, options = {}) => {
      if (url === "/api/assistant") {
        const payload = JSON.parse(options.body);
        commands.push(payload.command);
        if (commands.length === 1) {
          return await new Promise((resolve) => {
            finishFirstRequest = () => resolve(jsonResponse({ response: "First request completed." }));
          });
        }
        return jsonResponse({ response: "Second request completed." });
      }
      return originalFetch(url, options);
    };

    input.value = "First pending message";
    document.querySelector("#chatForm").dispatchEvent(
      new window.Event("submit", { bubbles: true, cancelable: true })
    );
    await wait(0);
    assert(commands.length === 1, "first chat request did not start");

    input.value = "Second message that must remain in the composer";
    document.querySelector("#chatForm").dispatchEvent(
      new window.Event("submit", { bubbles: true, cancelable: true })
    );
    assert(
      input.value === "Second message that must remain in the composer",
      "a message submitted while AJARVIS was busy was cleared"
    );
    assert(commands.length === 1, "a second assistant request started before the first finished");

    finishFirstRequest();
    await wait(30);
    document.querySelector("#chatForm").dispatchEvent(
      new window.Event("submit", { bubbles: true, cancelable: true })
    );
    await wait(30);
    assert(commands.length === 2 && commands[1] === "Second message that must remain in the composer",
      "preserved draft was not sent after the first reply completed");
    successes.push("busy chat preserves the unsent draft and allows retry after completion");
  } finally {
    app.dom.window.close();
  }
}

async function testHistoryInitialLoadRetry() {
  const app = await mountPage("history", { failInitialHistory: true });
  try {
    const { document } = app;
    const retry = document.querySelector("#loadOlderHistory");
    assert(retry && !retry.hidden && !retry.disabled, "history: initial load failure did not expose an enabled retry");
    assert(retry.textContent === "Retry loading history", "history: initial retry label is incorrect");
    retry.click();
    await wait(30);
    assert(document.querySelector("#historyList").textContent.includes("Newest saved question"),
      "history: retry after initial failure did not load conversations");
    assert(retry.textContent === "Load older exchanges", "history: retry label was not reset after success");
    successes.push("history initial-load failure exposes a working retry");
  } finally {
    app.dom.window.close();
  }
}

async function testFeatureForms() {
  const tasks = await mountPage("tasks");
  try {
    tasks.document.querySelector("#taskTitle").value = "QA smoke task";
    tasks.document.querySelector("#taskForm").dispatchEvent(new tasks.window.Event("submit", { bubbles: true, cancelable: true }));
    await wait(25);
    assert(tasks.calls.some((call) => call.url === "/api/tasks" && call.method === "POST"), "task form did not submit");
    successes.push("task creation form");
  } finally { tasks.dom.window.close(); }

  const notes = await mountPage("notes");
  try {
    notes.document.querySelector("#noteText").value = "QA smoke note";
    notes.document.querySelector("#noteForm").dispatchEvent(new notes.window.Event("submit", { bubbles: true, cancelable: true }));
    await wait(25);
    assert(notes.calls.some((call) => call.url === "/api/notes" && call.method === "POST"), "note form did not submit");
    successes.push("personal notes creation form");
  } finally { notes.dom.window.close(); }

  const memory = await mountPage("memory");
  try {
    memory.document.querySelector("#preferenceKey").value = "answer_style";
    memory.document.querySelector("#preferenceValue").value = "concise";
    memory.document.querySelector("#preferenceForm").dispatchEvent(new memory.window.Event("submit", { bubbles: true, cancelable: true }));
    await wait(25);
    assert(memory.calls.some((call) => call.url === "/api/preferences" && call.method === "POST"), "memory form did not submit");
    successes.push("personal memory form");
  } finally { memory.dom.window.close(); }

  const settings = await mountPage("settings");
  try {
    const language = settings.document.querySelector("#voiceLanguage");
    language.value = "ta-IN";
    language.dispatchEvent(new settings.window.Event("change", { bubbles: true }));
    assert(settings.window.localStorage.getItem("ajarvis.voice.language") === "ta-IN", "voice language preference was not persisted");
    const toggle = settings.document.querySelector("#voiceOutput");
    toggle.checked = false;
    toggle.dispatchEvent(new settings.window.Event("change", { bubbles: true }));
    assert(settings.window.localStorage.getItem("ajarvis.voice.output") === "false", "spoken-reply preference was not persisted");
    successes.push("voice settings persistence");
  } finally { settings.dom.window.close(); }
}

async function testMutationFormGuards() {
  const cases = [
    {
      page: "tasks", formId: "taskForm", buttonSelector: 'button[type="submit"]',
      endpoint: "/api/tasks", fields: { taskTitle: "Guarded task" },
      success: { task: { id: 1, title: "Guarded task", details: "", done: false } },
      disabledLabel: "Adding…",
    },
    {
      page: "notes", formId: "noteForm", buttonSelector: 'button[type="submit"]',
      endpoint: "/api/notes", fields: { noteText: "Guarded note" },
      success: { ok: true, note: { id: 1, text: "Guarded note" } },
      disabledLabel: "Saving…",
    },
    {
      page: "memory", formId: "preferenceForm", buttonSelector: 'button[type="submit"]',
      endpoint: "/api/preferences", fields: { preferenceKey: "answer_style", preferenceValue: "concise" },
      success: { preference: { key: "answer_style", value: "concise" } },
      disabledLabel: "Saving…",
    },
  ];

  for (const item of cases) {
    const app = await mountPage(item.page);
    try {
      const { window, document, calls } = app;
      const form = document.querySelector("#" + item.formId);
      const button = form.querySelector(item.buttonSelector);
      for (const [id, value] of Object.entries(item.fields)) document.querySelector("#" + id).value = value;
      const originalFetch = window.fetch;
      let finishRequest;
      let postCount = 0;
      window.fetch = async (url, options = {}) => {
        if (url === item.endpoint && String(options.method || "GET").toUpperCase() === "POST") {
          postCount += 1;
          return await new Promise((resolve) => {
            finishRequest = () => resolve(jsonResponse(item.success, 201));
          });
        }
        return originalFetch(url, options);
      };

      form.dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
      await wait(0);
      assert(form.dataset.submitting === "true", item.page + ": form did not enter its submitting state");
      assert(button.disabled && button.textContent === item.disabledLabel, item.page + ": submit button did not show its busy state");

      form.dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
      assert(postCount === 1, item.page + ": duplicate submission reached the API");

      finishRequest();
      await wait(30);
      assert(!button.disabled && !form.dataset.submitting, item.page + ": form did not recover after the request");
      successes.push("duplicate-submit guard: " + item.page);
    } finally {
      app.dom.window.close();
    }
  }
}

async function testTaskSaveRefreshFailureIsReportedSeparately() {
  const app = await mountPage("tasks");
  try {
    const { window, document } = app;
    const originalFetch = window.fetch;
    window.fetch = async (url, options = {}) => {
      if (url === "/api/tasks" && String(options.method || "GET").toUpperCase() === "POST") {
        return jsonResponse({ task: { id: 7, title: "Persisted task" } }, 201);
      }
      if (url === "/api/tasks" && String(options.method || "GET").toUpperCase() === "GET") {
        return jsonResponse({ error: "Task list refresh failed." }, 503);
      }
      return originalFetch(url, options);
    };
    document.querySelector("#taskTitle").value = "Persisted task";
    document.querySelector("#taskForm").dispatchEvent(
      new window.Event("submit", { bubbles: true, cancelable: true })
    );
    await wait(35);
    const messages = document.querySelector("#toastRegion").textContent;
    assert(messages.includes("Task saved."), "task: successful save was not acknowledged separately from refresh");
    assert(messages.includes("Your task was saved, but the task list could not refresh."), "task: refresh failure was misreported as a save failure");
    successes.push("task save success is preserved when list refresh fails");
  } finally {
    app.dom.window.close();
  }
}

async function testDocumentAndVisualFlows() {
  const documents = await mountPage("documents");
  try {
    const upload = documents.document.querySelector("#documentFile");
    const file = new documents.window.File(["AJARVIS QA document"], "qa.txt", { type: "text/plain" });
    Object.defineProperty(upload, "files", { configurable: true, value: [file] });
    documents.document.querySelector("#documentForm").dispatchEvent(
      new documents.window.Event("submit", { bubbles: true, cancelable: true })
    );
    await wait(35);
    assert(documents.calls.some((call) => call.url === "/api/documents" && call.method === "POST"), "document upload did not call the API");
    assert(documents.document.querySelector("#documentResult").textContent.includes("Document accepted for QA."), "document result was not rendered");
    successes.push("document upload and analysis response");
  } finally { documents.dom.window.close(); }

  const oversized = await mountPage("documents");
  try {
    const upload = oversized.document.querySelector("#documentFile");
    const file = new oversized.window.File([new Uint8Array(8 * 1024 * 1024 + 1)], "large.txt", { type: "text/plain" });
    Object.defineProperty(upload, "files", { configurable: true, value: [file] });
    oversized.document.querySelector("#documentForm").dispatchEvent(
      new oversized.window.Event("submit", { bubbles: true, cancelable: true })
    );
    await wait(20);
    assert(!oversized.calls.some((call) => call.url === "/api/documents" && call.method === "POST"), "oversized document bypassed the 8 MB client limit");
    successes.push("document upload size validation");
  } finally { oversized.dom.window.close(); }

  const visual = await mountPage("visual");
  try {
    const image = new visual.window.File(["fake image bytes"], "qa.png", { type: "image/png" });
    Object.defineProperty(visual.document.querySelector("#visualFile"), "files", { configurable: true, value: [image] });
    visual.document.querySelector("#visualFile").dispatchEvent(new visual.window.Event("change", { bubbles: true }));
    assert(!visual.document.querySelector("#visualAnalyzeButton").disabled, "visual analysis did not enable after image selection");
    visual.document.querySelector("#visualPrompt").value = "Describe this QA test image.";
    visual.document.querySelector("#visualAnalyzeButton").click();
    await wait(30);
    assert(visual.calls.some((call) => call.url === "/api/visual/analyze" && call.method === "POST"), "visual analysis did not call the API");
    assert(visual.document.querySelector("#visualResult").textContent.includes("A QA sample image."), "visual answer was not rendered");
    successes.push("visual image selection and analysis response");
  } finally { visual.dom.window.close(); }

  const oversizedImage = await mountPage("visual");
  try {
    const image = new oversizedImage.window.File([new Uint8Array(5 * 1024 * 1024 + 1)], "large.png", { type: "image/png" });
    Object.defineProperty(oversizedImage.document.querySelector("#visualFile"), "files", { configurable: true, value: [image] });
    oversizedImage.document.querySelector("#visualFile").dispatchEvent(new oversizedImage.window.Event("change", { bubbles: true }));
    oversizedImage.document.querySelector("#visualAnalyzeButton").click();
    await wait(20);
    assert(!oversizedImage.calls.some((call) => call.url === "/api/visual/analyze"), "oversized image bypassed the 5 MB client limit");
    successes.push("visual image size validation");
  } finally { oversizedImage.dom.window.close(); }
}

async function testLocalSpeechRecoveryWhenMicrophoneIsMissing() {
  const source = fs.readFileSync(path.join(__dirname, "..", "static", "cloud-dashboard.js"), "utf8");
  const errorStart = source.indexOf("recognition.onerror = (event) => {");
  const endMarker = "\n      recognition.onend = () => {";
  const errorEnd = source.indexOf(endMarker, errorStart);
  const onendStart = errorEnd + endMarker.length - "recognition.onend = () => {".length;
  const onendEnd = source.indexOf("\n      recognition.onresult = async (event) => {", onendStart);
  const clickStart = source.indexOf("document.getElementById('ai-core').addEventListener('click', () => {");
  const clickEnd = source.indexOf("\n      });\n    } else {", clickStart);
  assert(errorStart >= 0 && errorEnd > errorStart, "desktop voice: error handler could not be extracted");
  assert(onendEnd > onendStart, "desktop voice: onend handler could not be extracted");
  assert(clickStart >= 0 && clickEnd > clickStart, "desktop voice: manual retry handler could not be extracted");

  const dom = new JSDOM('<!doctype html><div id="ai-core"></div><div id="mic-status"></div>', {
    url: "http://127.0.0.1:5000/dashboard",
    runScripts: "outside-only",
    pretendToBeVisual: true,
  });
  const { window } = dom;
  window.__qa = { stoppedStreams: 0, restartRequests: 0, recognitionStarts: 0 };
  window.speechSynthesis = { speaking: false, cancel() {} };
  const handlers = source.slice(errorStart, errorEnd)
    + "\n" + source.slice(onendStart, onendEnd)
    + "\n" + source.slice(clickStart, clickEnd) + "\n      });";
  window.eval(
    'let recognitionStarting = false;\n' +
    'let recognitionActive = false;\n' +
    'let recognitionStartWatchdog = null;\n' +
    'let recognitionBlocked = false;\n' +
    'let shouldListen = true;\n' +
    'let speechHold = false;\n' +
    'let speechGeneration = 0;\n' +
    'let recognitionRestartTimer = null;\n' +
    'let audioContext = null;\n' +
    'const aiStatus = { textContent: "" };\n' +
    'const statusText = document.getElementById("mic-status");\n' +
    'const voiceLanguageSelect = { value: "en-IN" };\n' +
    'const stopSpeechButton = { disabled: true };\n' +
    'const recognition = { lang: "en-IN", start() { window.__qa.recognitionStarts += 1; } };\n' +
    'function showToast() {}\n' +
    'function stopMicReactiveSystem() { if (window.__qa.stoppedStreams === 0) window.__qa.stoppedStreams += 1; }\n' +
    'function scheduleRecognitionRestart() { if (shouldListen && !recognitionBlocked) window.__qa.restartRequests += 1; }\n' +
    'function startRecognitionSafely() { if (!shouldListen || recognitionBlocked) return false; recognition.start(); return true; }\n' +
    'window.__qaCounters = () => ({ recognitionBlocked, shouldListen, ...window.__qa, status: statusText.textContent });\n' +
    handlers + '\n' +
    'recognition.onerror({ error: "audio-capture" });\n' +
    'recognition.onend();'
  );
  let state = window.__qaCounters();
  assert(state.recognitionBlocked && !state.shouldListen, "desktop voice: missing microphone did not block automatic restarts");
  assert(state.stoppedStreams === 1, "desktop voice: microphone visualizer was not stopped");
  assert(state.restartRequests === 0, "desktop voice: onend scheduled a restart without a microphone");
  assert(state.status.includes("TAP THE CORE TO RETRY"), "desktop voice: missing microphone recovery instruction is absent");

  window.document.getElementById("ai-core").click();
  state = window.__qaCounters();
  assert(!state.recognitionBlocked && state.shouldListen, "desktop voice: reactor tap did not unblock speech recognition");
  assert(state.recognitionStarts === 1, "desktop voice: reactor tap did not start recognition exactly once");
  successes.push("desktop microphone-missing recovery blocks restart loop and restores manual retry");
  dom.window.close();
}

async function testLocalMicrophoneVisualizerLifecycle() {
  const localDashboard = fs.readFileSync(path.join(__dirname, "..", "static", "cloud-dashboard.js"), "utf8");
  const start = localDashboard.indexOf("/* MIC REACTIVE EFFECT");
  assert(start >= 0, "local dashboard: microphone visualizer block is missing");
  const source = localDashboard.slice(start);

  const dom = new JSDOM('<!doctype html><div id="ai-core"></div><div class="bar"></div><div class="bar"></div>', {
    url: "https://ajarvis.test/dashboard",
    runScripts: "outside-only",
    pretendToBeVisual: true,
  });
  const { window } = dom;
  let getUserMediaCalls = 0;
  let tracksStopped = 0;
  let contextsCreated = 0;
  let contextsClosed = 0;
  let disconnected = 0;
  let cancelledFrames = 0;
  let nextFrame = 0;
  window.navigator.mediaDevices = {
    getUserMedia: async () => {
      getUserMediaCalls += 1;
      return { getTracks: () => [{ stop: () => { tracksStopped += 1; } }] };
    },
  };
  window.requestAnimationFrame = () => ++nextFrame;
  window.cancelAnimationFrame = () => { cancelledFrames += 1; };
  window.AudioContext = class FakeAudioContext {
    constructor() { contextsCreated += 1; this.state = "running"; }
    createAnalyser() {
      return {
        fftSize: 0,
        frequencyBinCount: 8,
        getByteFrequencyData(target) { target.fill(96); },
      };
    }
    createMediaStreamSource() {
      return { connect() {}, disconnect() { disconnected += 1; } };
    }
    async resume() { this.state = "running"; }
    async close() { this.state = "closed"; contextsClosed += 1; }
  };
  window.eval(
    'const core = document.getElementById("ai-core"); const bars = document.querySelectorAll(".bar");\n' + source
  );
  await Promise.all([
    window.eval("startMicReactiveSystem()"),
    window.eval("startMicReactiveSystem()"),
  ]);
  assert(getUserMediaCalls === 1, "local dashboard: repeated recognition starts opened multiple microphone streams");
  assert(contextsCreated === 1, "local dashboard: repeated recognition starts created multiple AudioContexts");
  await window.eval("startMicReactiveSystem()");
  assert(getUserMediaCalls === 1, "local dashboard: existing visualizer was not reused");
  await window.eval("stopMicReactiveSystem()");
  assert(tracksStopped === 1, "local dashboard: microphone track was not released");
  assert(contextsClosed === 1, "local dashboard: AudioContext was not closed");
  assert(disconnected === 1, "local dashboard: microphone source was not disconnected");
  assert(cancelledFrames === 1, "local dashboard: animation frame was not cancelled");
  successes.push("local Windows dashboard microphone visualizer reuse and cleanup");
  dom.window.close();
}

async function testLocalTextCommandNetworkRecovery() {
  const inlineScript = fs.readFileSync(path.join(__dirname, "..", "static", "cloud-dashboard.js"), "utf8");

  const start = inlineScript.indexOf("async function executeTextCommand() {");
  const end = inlineScript.indexOf('\n    textInput.addEventListener("keydown"', start);
  assert(start >= 0 && end > start, "local dashboard: text command handler is missing");
  const handler = inlineScript.slice(start, end);

  const dom = new JSDOM(
    '<!doctype html><input id="text-command-input"><button id="send-command-btn"></button><div id="transcript-box"></div>',
    { url: "https://ajarvis.test/dashboard", runScripts: "outside-only" }
  );
  const { window } = dom;
  window.eval(
    'const textInput = document.getElementById("text-command-input");' +
    'const sendBtn = document.getElementById("send-command-btn");' +
    'const transcriptBox = document.getElementById("transcript-box");' +
    'let processCommand = async () => null;\n' +
    handler +
    '\nwindow.runDesktopTextCommand = executeTextCommand;' +
    '\nwindow.setProcessCommand = (fn) => { processCommand = fn; };'
  );

  const input = window.document.getElementById("text-command-input");
  const button = window.document.getElementById("send-command-btn");
  input.value = "open the vessel checklist";
  await window.runDesktopTextCommand();
  assert(
    input.value === "open the vessel checklist",
    "local dashboard: failed network request discarded the typed command"
  );
  assert(!button.disabled, "local dashboard: send button stayed disabled after failure");

  window.setProcessCommand(async () => "Opened the checklist.");
  await window.runDesktopTextCommand();
  assert(input.value === "", "local dashboard: successful command was not cleared");
  assert(!button.disabled, "local dashboard: send button stayed disabled after success");

  // A newer draft typed while the original request is in flight must win.
  let finishRequest;
  window.setProcessCommand(() => new Promise((resolve) => { finishRequest = () => resolve(null); }));
  input.value = "first message";
  const pending = window.runDesktopTextCommand();
  await wait(0);
  input.value = "newer draft";
  finishRequest();
  await pending;
  assert(input.value === "newer draft", "local dashboard: retry restoration overwrote a newer draft");

  successes.push("desktop typed-command network failure preserves retry text and newer drafts");
  dom.window.close();
}

async function testAuthenticationPages() {
  const css = fs.readFileSync(path.join(__dirname, "..", "static", "cloud.css"), "utf8");
  assert(css.includes("@keyframes auroraWaveDrift"), "login: animated aurora keyframes are missing");
  assert(css.includes("prefers-reduced-motion"), "login: reduced-motion support is missing");

  for (const page of ["login", "register"]) {
    const html = fs.readFileSync(path.join(fixtureDir, page + ".html"), "utf8");
    const dom = new JSDOM(html, {
      url: "https://ajarvis.test/" + page,
      runScripts: "outside-only",
      pretendToBeVisual: true,
    });
    const { window } = dom;
    let captured = null;
    window.fetch = async (url, options) => {
      captured = { url, options, body: JSON.parse(options.body) };
      return {
        ok: false,
        status: page === "login" ? 401 : 400,
        json: async () => ({ error: "Expected QA authentication rejection." }),
      };
    };
    const script = window.document.querySelector("script");
    assert(window.document.querySelector(".auth-aurora-waves"), page + ": aurora background is missing");
    assert(window.document.querySelector(".auth-product-title")?.textContent === "AJARVIS", page + ": product title is incorrect");
    assert(!window.document.body.textContent.includes("Secure Cloud Access"), page + ": generic access heading remains");
    assert(!window.document.body.textContent.includes("Welcome back"), page + ": generic welcome heading remains");
    window.eval(script.textContent);
    window.document.querySelector("#username").value = "qa_user";
    window.document.querySelector("#password").value = page === "login" ? "qa-password" : "qa-password-123";
    window.document.querySelector("#authForm").dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
    await wait(25);
    assert(captured, page + ": form did not submit authentication request");
    assert(captured.url === (page === "login" ? "/api/auth/login" : "/api/auth/register"), page + ": wrong authentication endpoint");
    assert(captured.body.username === "qa_user", page + ": username was not submitted");
    assert(window.document.querySelector("#authError").textContent.includes("Expected QA authentication rejection."), page + ": authentication error was not displayed");
    dom.window.close();
  }
  successes.push("login/register form submission, error handling and animated aurora");
}

(async () => {
  for (const [page, route] of routes) await runPageSmoke(page, route);
  await testChatAndVoice();
  await testBusyChatPreservesDraft();
  await testHistoryInitialLoadRetry();
  await testFeatureForms();
  await testMutationFormGuards();
  await testTaskSaveRefreshFailureIsReportedSeparately();
  await testDocumentAndVisualFlows();
  await testLocalSpeechRecoveryWhenMicrophoneIsMissing();
  await testLocalMicrophoneVisualizerLifecycle();
  await testLocalTextCommandNetworkRecovery();
  await testAuthenticationPages();
  console.log("BROWSER_SMOKE_OK " + successes.length);
  successes.forEach((item) => console.log("PASS " + item));
})().catch((error) => {
  console.error("BROWSER_SMOKE_FAILED " + error.stack);
  process.exitCode = 1;
});
