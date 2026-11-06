"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM, VirtualConsole } = require("jsdom");

const root = __dirname;
const template = fs.readFileSync(path.join(root, "../templates/cloud_dashboard.html"), "utf8");
const cloudScript = fs.readFileSync(path.join(root, "../static/cloud.js"), "utf8");
const interfaceScript = fs.readFileSync(path.join(root, "../static/interface.js"), "utf8");

const pages = [
  "dashboard", "history", "tasks", "notes", "memory",
  "activity", "visual", "documents", "account", "settings"
];

function makeResponse(data, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => null },
    json: async () => data
  };
}

function createFetch(calls, state) {
  return async (input, options = {}) => {
    const url = String(input);
    const method = String(options.method || "GET").toUpperCase();
    calls.push({ url, method, headers: options.headers || {} });
    if (url === "/api/system") {
      return makeResponse({ cpu_percent: 7, memory_percent: 19 });
    }
    if (url === "/api/reminders/claim") {
      return makeResponse({ reminders: [] });
    }
    if (url === "/api/history" || url.startsWith("/api/history?")) {
      return makeResponse({
        history: [{ command: "saved question", response: "saved answer" }],
        latest_id: 42
      });
    }
    if (url === "/api/assistant") {
      const payload = JSON.parse(options.body || "{}");
      state.commands.push(payload);
      return makeResponse({ response: "Smoke test response for: " + payload.command });
    }
    if (url === "/api/tasks" && method === "GET") {
      return makeResponse({ tasks: state.tasks });
    }
    if (url === "/api/tasks" && method === "POST") {
      const item = JSON.parse(options.body || "{}");
      state.tasks.push({ id: state.tasks.length + 1, ...item, done: false });
      return makeResponse({ task: state.tasks[state.tasks.length - 1] }, 201);
    }
    if (url === "/api/notes" && method === "GET") {
      return makeResponse({ notes: state.notes });
    }
    if (url === "/api/notes" && method === "POST") {
      const item = JSON.parse(options.body || "{}");
      state.notes.push({ id: state.notes.length + 1, text: item.text, created_at: "2026-11-06T00:00:00Z" });
      return makeResponse({ note: state.notes[state.notes.length - 1] }, 201);
    }
    if (url === "/api/preferences" && method === "GET") {
      return makeResponse({ preferences: state.preferences });
    }
    if (url === "/api/preferences" && method === "POST") {
      const item = JSON.parse(options.body || "{}");
      state.preferences.push(item);
      return makeResponse({ preference: item }, 201);
    }
    if (url === "/api/activity") {
      return makeResponse({ activity: [{ tool_name: "read_status", outcome: "success", duration_ms: 4 }] });
    }
    if (url === "/api/documents") {
      return makeResponse({ documents: [] });
    }
    return makeResponse({ ok: true });
  };
}

function wait(ms = 15) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function runPage(page) {
  const virtualConsole = new VirtualConsole();
  const jsdomErrors = [];
  virtualConsole.on("jsdomError", (error) => jsdomErrors.push(error.message));
  const dom = new JSDOM(template, {
    url: "https://ajarvis.test/" + page,
    runScripts: "outside-only",
    pretendToBeVisual: true,
    virtualConsole
  });
  const { window } = dom;
  const calls = [];
  const state = { commands: [], tasks: [], notes: [], preferences: [] };
  const uncaught = [];

  window.document.body.dataset.user = "qa-user";
  window.document.body.dataset.csrf = "qa-csrf-token";
  window.document.body.dataset.page = page;
  window.setInterval = () => 1;
  window.clearInterval = () => {};
  window.fetch = createFetch(calls, state);
  window.speechSynthesis = {
    cancel() {},
    getVoices() { return []; },
    speak(utterance) {
      if (typeof utterance.onstart === "function") utterance.onstart();
      if (typeof utterance.onend === "function") utterance.onend();
    }
  };
  window.SpeechSynthesisUtterance = class {
    constructor(text) { this.text = text; }
  };
  window.addEventListener("error", (event) => uncaught.push(event.message));
  window.addEventListener("unhandledrejection", (event) => uncaught.push(String(event.reason)));

  window.eval(cloudScript);
  window.eval(interfaceScript);
  await wait(35);

  assert.equal(uncaught.length, 0, page + " produced an uncaught browser error: " + uncaught.join("; "));
  assert.equal(jsdomErrors.length, 0, page + " produced a jsdom runtime error: " + jsdomErrors.join("; "));
  assert.ok(calls.some((call) => call.url === "/api/system"), page + " did not initialize system status");
  assert.ok(calls.some((call) => call.url === "/api/reminders/claim"), page + " did not initialize reminder checks");

  const expectedEndpoint = {
    history: "/api/history",
    tasks: "/api/tasks",
    notes: "/api/notes",
    memory: "/api/preferences",
    activity: "/api/activity",
    documents: "/api/documents"
  }[page];
  if (expectedEndpoint) {
    assert.ok(calls.some((call) => call.url === expectedEndpoint), page + " did not load its feature data");
  } else if (page === "dashboard") {
    assert.ok(!calls.some((call) => call.url === "/api/history"), "New Chat unexpectedly loaded saved history");
  }

  if (page === "history") {
    assert.match(window.document.getElementById("historyList").textContent, /saved question/);
    assert.match(window.document.getElementById("historyList").textContent, /saved answer/);
  }

  if (page === "dashboard") {
    const input = window.document.getElementById("commandInput");
    input.value = "text chat smoke test";
    window.document.getElementById("chatForm").dispatchEvent(
      new window.Event("submit", { bubbles: true, cancelable: true })
    );
    await wait(35);
    assert.equal(state.commands.length, 1, "Text chat did not reach the assistant API");
    assert.equal(state.commands[0].command, "text chat smoke test");
    assert.match(window.document.getElementById("chatLog").textContent, /Smoke test response/);

    class FakeSpeechRecognition {
      start() {
        window.setTimeout(() => {
          if (this.onstart) this.onstart();
          const results = [{ 0: { transcript: "voice command smoke test" }, isFinal: true }];
          this.onresult?.({ results });
          this.onend?.();
        }, 0);
      }
      stop() { this.onend?.(); }
    }
    window.SpeechRecognition = FakeSpeechRecognition;
    window.document.getElementById("micButton").click();
    await wait(50);
    assert.equal(state.commands.length, 2, "Voice transcript did not reach the assistant API");
    assert.equal(state.commands[1].command, "voice command smoke test");
    assert.equal(uncaught.length, 0, "Chat/voice interaction produced an uncaught error");
  }

  if (page === "tasks") {
    window.document.getElementById("taskTitle").value = "QA task";
    window.document.getElementById("taskForm").dispatchEvent(
      new window.Event("submit", { bubbles: true, cancelable: true })
    );
    await wait(25);
    assert.equal(state.tasks.length, 1, "Task form did not create a task");
  }

  if (page === "notes") {
    window.document.getElementById("noteText").value = "QA note";
    window.document.getElementById("noteForm").dispatchEvent(
      new window.Event("submit", { bubbles: true, cancelable: true })
    );
    await wait(25);
    assert.equal(state.notes.length, 1, "Notes form did not create a note");
  }

  if (page === "memory") {
    window.document.getElementById("preferenceKey").value = "qa_style";
    window.document.getElementById("preferenceValue").value = "Use concise answers";
    window.document.getElementById("preferenceForm").dispatchEvent(
      new window.Event("submit", { bubbles: true, cancelable: true })
    );
    await wait(25);
    assert.equal(state.preferences.length, 1, "Personal memory form did not save a preference");
  }

  if (page === "settings") {
    const language = window.document.getElementById("voiceLanguage");
    language.value = "ta-IN";
    language.dispatchEvent(new window.Event("change", { bubbles: true }));
    assert.equal(window.localStorage.getItem("ajarvis.voice.language"), "ta-IN");
    const voiceOutput = window.document.getElementById("voiceOutput");
    voiceOutput.checked = false;
    voiceOutput.dispatchEvent(new window.Event("change", { bubbles: true }));
    assert.equal(window.localStorage.getItem("ajarvis.voice.output"), "false");
  }

  dom.window.close();
}

(async () => {
  for (const page of pages) {
    await runPage(page);
    process.stdout.write("PASS browser initialization and feature smoke: " + page + "\n");
  }
  process.stdout.write("PASS dashboard text chat and simulated microphone transcript\n");
  process.stdout.write("PASS task, note, memory and settings interactions\n");
})().catch((error) => {
  console.error(error && error.stack ? error.stack : error);
  process.exitCode = 1;
});
