# A.J.A.R.V.I.S. — AI Personal Assistant

A local Windows-focused assistant application using Flask, Google Gemini integration, MySQL, and face-authentication components.

## Features

- Flask web interface with login, registration, and dashboard pages
- Gemini-backed assistant/command integration
- Face-authentication and camera-streaming components
- MySQL persistence and command/memory-related modules
- System resource statistics
- Explicit, editable, user-scoped personal memory for facts and answer preferences
- Relevant conversation context, follow-up resolution, and read-only memory retrieval tools
- Bounded multi-step task planning with per-step approvals for computer-changing actions
- User-scoped automation activity history that omits raw arguments and tool outputs

## Tech Stack

Python · Flask · Google GenAI · OpenCV · face-recognition · MySQL · python-dotenv

## Setup

1. Install a supported Python version and the system prerequisites required by `face-recognition` and its dependencies.
2. Create and activate a virtual environment.
3. Install packages:

   ```bash
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. Copy `.env.example` to `.env`. Set a unique random `SECRET_KEY` and your MySQL credentials. `GEMINI_API_KEY` is needed for free-form Gemini answers but is no longer required just to start local commands; `WEATHER_API_KEY` is optional.
5. For a new database, create the tables using `database/schema.sql`. For an existing database, back it up and follow [the database upgrade runbook](database/migrations/README.md) to add user-scoped history and personal memory while preserving users and face encodings.
6. Start the app:

   ```bash
   python app.py
   ```

## Safer Desktop Controls

Shutdown and restart requests need an exact confirmation within 30 seconds: say `shutdown system`, then `confirm shutdown`. Say `cancel` to cancel. The initial request alone does not execute the action.

## Automated Tests

From this directory, set `SECRET_KEY` and run `python -m pip install -r requirements-web.txt mysql-connector-python`, followed by `pytest -q tests`. GitHub Actions checks both dashboard JavaScript surfaces, the Render Blueprint, Python compilation, telemetry, and local authentication/command integration. Camera hardware and biometric accuracy still require testing on the target Windows device.

## User-Scoped History

Command history, AI context, analytics, notes, activation state, and explicit personal memories are scoped to the authenticated username. Saved memories can be created, reviewed, updated, and deleted in the local dashboard or with commands such as `remember my answer style is concise`, `what do you remember about me?`, and `forget my answer style`. A memory is sent to the configured Gemini model as contextual data during free-form AI requests; it is not authorization or executable instruction. Never store credentials. Legacy history rows remain unassigned after migration so they are not exposed to another account.

## Security and Privacy

- Keep `.env` out of version control; never publish API keys or database credentials.
- Do not use a predictable fallback secret key in a deployed environment.
- Disable Flask debug mode outside local development and configure secure session-cookie settings.
- Local face login now requires exactly one detected face, a fresh camera frame, and the same identity matched on two distinct frames. Stale frames, multiple faces, unknown faces, and recognition errors fail closed.
- Face recognition still has no liveness detection and can be spoofed with a suitable photo/video. Use informed consent, protect the biometric database, and do not treat face recognition alone as high-assurance identity verification. `FACE_MATCH_THRESHOLD` defaults to 0.55; lower values are stricter and must be validated with consented samples under the target camera and lighting conditions.

## Main Components

- `app.py` — Flask routes and application entry point
- `config.py` — environment-based configuration
- `database/` — database access
- `intelligence/` — command routing and assistant memory
- `security/` — camera, face-authentication, and session modules
- `system/` — system statistics
- `templates/` and `static/` — web interface

See the repository-level README for the full project overview and setup.


## Tool-Enabled Agent Foundation

The AI fallback now uses manual Gemini function calling through an explicit allow-list in `intelligence/tool_registry.py` and `intelligence/agent.py`.

The initial agent can read the current date/time, CPU and memory usage, home-disk usage, battery status, and the signed-in user's saved notes (recent notes or phrase search). Calls are validated against registered argument schemas, and the agent limits the number of tool calls and the amount of returned data. Automatic SDK function execution is disabled so the application, not the model, decides whether a requested tool can run.

Only read-only tools are automatically eligible. Unknown tools, invalid arguments, and tools marked as side-effecting or destructive are rejected. When the note or memory tools are used, matching content is sent to the configured Gemini model for an answer; do not store passwords, API keys, tokens, or other secrets in notes or personalization memory. The model cannot execute arbitrary Python, shell commands, or file paths through this interface. The separate Phase 5 task planner now offers a small registered action allow-list behind trusted, one-time approvals. The ordinary Gemini chat/tool path remains read-only and cannot directly invoke side-effecting tools.

Requests containing wording such as `search the web`, `latest`, `current`, or `recent` are routed through `intelligence/web_research.py`, a separate Google Search-grounded Gemini request. The response includes up to five validated HTTP(S) source links when grounding metadata is available. This requires `GEMINI_API_KEY`; the default model is `gemini-2.5-flash`, and `GEMINI_WEB_MODEL` can override it. Gemini API usage charges may apply. When no source metadata is returned, AJARVIS says it could not verify source links.

Run the focused unit tests with:

```bash
pytest -q tests/test_tool_registry.py tests/test_agent.py tests/test_notes.py tests/test_web_research.py
```


## Phase 5 — Task Planning & Controlled Automation

The local dashboard includes a **Task Planner & Controlled Automation** panel. Enter a task in natural language, such as:

- "Check my battery and system status."
- "Check my system status, then open https://openai.com."
- "Open Calculator, then check my battery."

AJARVIS asks Gemini for a structured plan of at most five steps, then validates every tool name and argument against the application's registered tool catalogue. The model does not execute tools or supply shell commands.

### Execution and approval rules

- Registered read-only checks (date/time, system and battery status, and the signed-in user's saved notes or memories) may run automatically after you submit a task.
- Opening a website is available only for public HTTPS URLs. Embedded credentials, local hostnames, and private/local IP destinations are rejected.
- On Windows, the planner can request Calculator, Notepad, File Explorer, Chrome, VS Code, or workstation locking. Application names are mapped to fixed executable identifiers; arbitrary executable paths and commands are not accepted.
- Each computer-changing step pauses until you approve that exact step in the dashboard. Approval tokens are one-time, bound to the signed-in username, and expire after 60 seconds. A plan expires after five minutes.
- Rejecting a step stops the rest of the plan. Cancellation prevents later steps from starting; an operation that has already started cannot be assumed to have been undone.
- Pending plans and approval tokens are kept in process memory and are discarded on application restart. This fails closed: a user must create and approve a new plan after a restart.
- The activity table records per-user event metadata (tool name, event type and a short generic summary). It deliberately does not persist task prompts, URLs, raw arguments, note contents, or tool results.

The agent chat tool-call path remains read-only. The planner is a separate, server-validated workflow; it does not offer arbitrary shell execution, unrestricted file editing, email sending, or autonomous background operation. Use the dashboard's activity panel to review recent planner events.

For existing MySQL installations, back up the database, review the dry run, and apply `python database/migrate_database.py --apply` as described in [the database upgrade runbook](database/migrations/README.md). The migration creates the privacy-minimal `automation_activity` table and its per-user index if they are missing.


## Phase 6 — Proactive Intelligence & Workflow Memory

The local dashboard now supports persistent scheduled reminders, opt-in notifications, and durable workflow status history.

### Reminders and notifications

- Create reminders with a title and a timezone-aware future date/time (up to one year ahead). AJARVIS stores the due time in UTC and displays it in the browser's local timezone.
- Reminders are stored in MySQL and remain available across application restarts.
- Reminder alerts and browser notifications are both disabled by default. Enable reminder alerts in the dashboard; browser notifications require a separate opt-in and the browser's site permission.
- When the dashboard is open, it checks for due reminders once per minute. Due reminders also surface in the in-app Notification Centre. If AJARVIS is closed when a reminder becomes due, it is collected the next time the dashboard is opened; native browser pop-ups are not delivered while the dashboard is closed.
- Mark reminders completed or cancelled, and mark delivered notifications read. Notification and reminder APIs are scoped to the authenticated account and write endpoints require CSRF validation.

### Durable workflow history and recovery

- Automation workflow metadata (workflow status, step count, safe tool identifiers and timestamps) is stored separately from the detailed execution plan.
- The system deliberately does not persist user prompts, URLs, raw tool arguments, note contents, model outputs, approval tokens or executable parameters.
- When the local app starts, workflows left ready/running/awaiting approval by an older process are marked `interrupted`.
- Interrupted workflows are review-only. Create a fresh plan rather than automatically replaying actions after a crash or restart. This prevents duplicate browser launches or other side effects.
- Completed and interrupted workflow status remains available in the dashboard's Durable Workflow History panel.

### Existing MySQL installation

Back up the database, review the read-only migration preview, then apply the Phase 6 schema changes with `python database/migrate_database.py --apply` and type `MIGRATE` after checking the target database name. Verify with `python database/verify_schema.py` and run `pytest -q tests`. The migration adds durable workflow, reminder, notification preference and notification tables without dropping existing users, face encodings, personal memory or automation audit history.

## Local Voice Command Flow

The local Windows dashboard follows a guarded activation flow: say "Hey Jarvis" to wake it, then say "system activate" before desktop commands. You can also say "Hey Jarvis, system activate" in one utterance. Once activated, leading wake phrases are removed before command routing so "Hey Jarvis, what time is it?" and "Hey Jarvis, take a note: ..." still reach the intended command handler.

The local dashboard offers voice-language selection for English (India), English (US), Tamil, and Hindi, plus a spoken-replies toggle and a stop-voice control. Availability depends on the browser's SpeechRecognition support, microphone permissions, selected language support, and installed speech voices. AJARVIS pauses recognition during spoken replies to reduce feedback loops where it hears and repeats its own response. This is browser speech recognition, not a guaranteed always-on offline wake-word engine.

## Hosted Cloud Mode

Use cloud_app.py and requirements-web.txt for the Render-hosted workspace. The cloud version uses password accounts and PostgreSQL storage for notes, editable user preferences, tasks, reminders, document text, and history. Personal preferences are visible and removable from the dashboard. The Agent Activity panel records executed tool names, outcome and duration without recording tool arguments or private note/document contents. It does not import the camera or Windows desktop-control entry points used by app.py. Deployment is configured by the repository-root render.yaml file.

### Voice command console

The hosted dashboard uses browser-based speech recognition and speech synthesis. Press the microphone button to start a voice session, select English (India), English (US), Tamil, or Hindi, and use the status indicator to see when AJARVIS is listening, analyzing, or speaking. Spoken replies can be muted or stopped. Simple commands can save/read notes and create/list tasks. A leading "Hey Jarvis" phrase is accepted after the mic has been pressed; there is no always-on wake-word listener in cloud mode. Voice support depends on browser/device support and microphone permissions. A spoken "remind me to ..." request creates a task without a scheduled time; set a date and time in Tasks & Reminders to schedule a notification.

Assistant requests are rate-limited per signed-in account to help protect free API quota. The cloud app still cannot control your local computer; desktop automation must remain in the separate local app and requires explicit safety design.

See [CLOUD_DEPLOYMENT.md](CLOUD_DEPLOYMENT.md) before applying the Blueprint, especially its cost, ephemeral service, Gemini API, and data-retention notes.
