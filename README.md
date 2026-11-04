# A.J.A.R.V.I.S. — AI Personal Assistant

![Python CI](https://github.com/ajayyy11/AJARVIS-An-AI-Personal-Voice-Assistant-/actions/workflows/ci.yml/badge.svg)

A local assistant project for Windows built with Flask, Google Gemini integration, MySQL support, and face-authentication components. The application source is located in the `A.JARVIS/` directory.

## Project Highlights

- Flask-based web interface and dashboard
- Gemini-powered assistant with bounded, allow-listed read-only tools and grounded web research
- Face-authentication workflow using computer-vision libraries
- MySQL database connection layer
- User-scoped command history, AI context, notes, activation state, and editable personal memory
- Multi-step task planning with a controlled allow-list and per-step user approval for computer-changing actions
- Persistent reminders, opt-in browser notifications, and workflow recovery history
- User-owned projects, transparent task prioritisation, and a personal focus brief
- User-triggered multimodal visual understanding for image/PDF analysis, one-shot camera/screen snapshots, and scanned-PDF text extraction
- Session management and system-statistics modules

## Tech Stack

Python · Flask · Google GenAI · OpenCV · face-recognition · MySQL

## Hosted Cloud Workspace

A separate cloud entry point is available at A.JARVIS/cloud_app.py. The hosted cloud workspace is deployed at https://ajarvis-cloud.onrender.com using Render Free, an external PostgreSQL database on Neon, and a Gemini API key where free quota is available. Free tiers have usage limits and may sleep; see A.JARVIS/CLOUD_DEPLOYMENT.md for setup, limitations, and troubleshooting.

Deployment configuration and setup steps are in [the cloud deployment guide](A.JARVIS/CLOUD_DEPLOYMENT.md). The root [Render Blueprint](render.yaml) defines a free Render web service only; it does not create a Render-managed database. `DATABASE_URL` points to the external Neon PostgreSQL database, and `GEMINI_API_KEY` is configured privately in Render. Gemini API quotas vary, so do not enable paid billing if you need to keep costs at ₹0.

The cloud app depends on the Render-provided DATABASE_URL, a generated SECRET_KEY, and a manually configured GEMINI_API_KEY for AI features. Never commit live secrets.

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/ajayyy11/AJARVIS-An-AI-Personal-Voice-Assistant-.git
cd AJARVIS-An-AI-Personal-Voice-Assistant-/A.JARVIS
```

### 2. Create a virtual environment

**Windows:**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**macOS/Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure the application

Copy `.env.example` to `.env`. Set a unique random `SECRET_KEY` and your MySQL credentials. `GEMINI_API_KEY` enables Gemini responses and grounded Google Search research; without it, local commands can still run but AI answers and web research are unavailable. `GEMINI_WEB_MODEL` optionally selects the model used for grounded web research (default: `gemini-2.5-flash`). `WEATHER_API_KEY` is optional and enables weather lookups. For a new database, create tables from `database/schema.sql`. For an existing installation, follow the step-by-step [database upgrade runbook](A.JARVIS/database/migrations/README.md); don't run the fresh-install schema over an existing database.

Never commit `.env`, API keys, database passwords, or real biometric data. Use a unique random secret key and disable debug mode in any deployment.

### 5. Run

```bash
python app.py
```

Follow any application-specific setup instructions in [the application README](A.JARVIS/README.md).

## Security and Privacy

This project handles camera input, face-related data, sessions, and API credentials. Use it only with informed consent, protect credentials, and review access controls before exposing it to a network. Face recognition can make mistakes and should not be treated as infallible identity verification.

## Agent Tool Safety

Gemini tool calls are handled manually through a local allow-list. The current agent tools provide read-only date/time, system/battery status, and user-scoped saved-note lookup. Commands containing explicit web-search or current-information wording use a separate Gemini Google Search-grounded request and display the available source URLs. Web research requires `GEMINI_API_KEY` and may incur API usage charges. Note content may be sent to the configured Gemini model when the notes tools are used, so do not store secrets in notes. Arbitrary shell execution and unrestricted file operations are not exposed. The Phase 5 task planner can coordinate registered read-only checks and a small host-specific action allow-list; every computer-changing planner step requires a one-time, user-bound approval in the local dashboard. The ordinary chat tool path remains read-only. See [the application agent notes](A.JARVIS/README.md#tool-enabled-agent-foundation).

## Safer Desktop Controls

Shutdown and restart requests now require an exact confirmation within 30 seconds. For example, say `shutdown system`, then `confirm shutdown`. Say `cancel` to cancel the pending action. The application does not execute shutdown or restart commands from the initial phrase alone.

## Automated Tests

GitHub Actions validates both dashboard JavaScript surfaces and the Render Blueprint, compiles the Python modules, and runs the session, memory, task-planner, approval, activity-log, reminder, workflow-recovery, migration, and command integration tests. To run the suite locally from the application directory:

```bash
cd A.JARVIS
python -m pip install Flask python-dotenv pytest mysql-connector-python
# Linux/macOS:
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
pytest -q tests
```

On Windows PowerShell, set the test secret before running pytest:

```powershell
$env:SECRET_KEY = python -c "import secrets; print(secrets.token_hex(32))"
pytest -q tests
```

Command history, AI context, analytics, notes, and activation state are scoped to the signed-in username. Existing database installations must apply the migration in the setup instructions before persistent history will work. These tests cover session validation, database history fallback/cleanup, and power-action confirmation. They do not replace full integration testing of the camera, face-recognition accuracy, MySQL schema, or external AI services.


## Personal Projects and Explainable Task Prioritisation

The local AJARVIS dashboard provides user-scoped projects and tasks, including objectives, due dates, estimated effort, and explicit priority selection. A deterministic 0–100 suggestion score explains its inputs (chosen priority, deadline urgency, quick-win estimate, and in-progress status). The assistant's personal-focus tool is read-only: it can review active projects and the next tasks but cannot modify their status or priority. Existing MySQL installations must apply the Phase 7 schema migration described in [the database upgrade runbook](A.JARVIS/database/migrations/README.md).


## Proactive Reminders and Workflow Recovery

The local Windows dashboard supports scheduled reminders and a Notification Centre. Reminder alerts are opt-in, and browser notifications require a separate browser permission. Due reminders are checked while the dashboard is open and surfaced in-app; if AJARVIS was closed at the due time, they are collected when the dashboard is opened again. Browser pop-ups are not sent while the dashboard is closed.

Workflow history stores status metadata without prompts, URLs, action arguments, private note contents, or approval tokens. On restart, unfinished workflows are marked interrupted and must be reviewed and replanned rather than automatically replayed. Existing MySQL installations must apply the Phase 6 migration in [the database upgrade runbook](A.JARVIS/database/migrations/README.md).

## Repository Layout

```text
A.JARVIS/       Application source, configuration, templates, and dependencies
ProjectDetails/ Supporting project materials
```

## Author

Ajay Shanmuga Sundaram
