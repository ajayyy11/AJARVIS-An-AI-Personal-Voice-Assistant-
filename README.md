# A.J.A.R.V.I.S. — AI Personal Assistant

![Python CI](https://github.com/ajayyy11/AJARVIS-An-AI-Personal-Voice-Assistant-/actions/workflows/ci.yml/badge.svg)

A local assistant project for Windows built with Flask, Google Gemini integration, MySQL support, and face-authentication components. The application source is located in the `A.JARVIS/` directory.

## Project Highlights

- Flask-based web interface and dashboard
- Gemini-powered assistant with bounded, allow-listed read-only tools and grounded web research
- Face-authentication workflow using computer-vision libraries
- MySQL database connection layer
- User-scoped command history, AI context, notes, and activation state
- Session management and system-statistics modules

## Tech Stack

Python · Flask · Google GenAI · OpenCV · face-recognition · MySQL

## Hosted Cloud Workspace

A separate cloud entry point is now available at A.JARVIS/cloud_app.py. It provides password-based accounts, a responsive workspace, user-scoped PostgreSQL notes, preferences and history, tasks/reminders, document extraction and Q&A, Gemini agent tools, a privacy-minimal activity log, and grounded web research. It intentionally does not enable camera authentication or remote control of the user's personal computer.

Deployment configuration and exact setup steps are in [the cloud deployment guide](A.JARVIS/CLOUD_DEPLOYMENT.md). The root [Render Blueprint](render.yaml) defines the hosted web service and managed PostgreSQL. Review its database plan and current cost before applying; the database uses a paid persistent plan, and Gemini API use may incur separate charges.

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

Gemini tool calls are handled manually through a local allow-list. The current agent tools provide read-only date/time, system/battery status, and user-scoped saved-note lookup. Commands containing explicit web-search or current-information wording use a separate Gemini Google Search-grounded request and display the available source URLs. Web research requires `GEMINI_API_KEY` and may incur API usage charges. Note content may be sent to the configured Gemini model when the notes tools are used, so do not store secrets in notes. Arbitrary shell execution is not exposed, and side-effecting tool requests are rejected until a trusted approval workflow exists. See [the application agent notes](A.JARVIS/README.md#tool-enabled-agent-foundation).

## Safer Desktop Controls

Shutdown and restart requests now require an exact confirmation within 30 seconds. For example, say `shutdown system`, then `confirm shutdown`. Say `cancel` to cancel the pending action. The application does not execute shutdown or restart commands from the initial phrase alone.

## Automated Tests

GitHub Actions validates the dashboard JavaScript syntax, compiles the Python modules, and runs the session, memory-persistence, activation-expiry, and power-confirmation tests. To run the suite locally from the application directory:

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

## Repository Layout

```text
A.JARVIS/       Application source, configuration, templates, and dependencies
ProjectDetails/ Supporting project materials
```

## Author

Ajay Shanmuga Sundaram
