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

async function mountPage(page) {
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
    stop() {}
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
    if (url === "/api/history") return jsonResponse({ history: state.history, latest_id: 42 });
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
    successes.push("text chat, fresh context boundary, voice transcript and reply rendering");
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
  await testFeatureForms();
  await testAuthenticationPages();
  console.log("BROWSER_SMOKE_OK " + successes.length);
  successes.forEach((item) => console.log("PASS " + item));
})().catch((error) => {
  console.error("BROWSER_SMOKE_FAILED " + error.stack);
  process.exitCode = 1;
});
