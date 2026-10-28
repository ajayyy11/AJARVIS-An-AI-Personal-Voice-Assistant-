# A.J.A.R.V.I.S. — AI Personal Assistant

![Python CI](https://github.com/ajayyy11/AJARVIS-An-AI-Personal-Voice-Assistant-/actions/workflows/ci.yml/badge.svg)

A local assistant project for Windows built with Flask, Google Gemini integration, MySQL support, and face-authentication components. The application source is located in the `A.JARVIS/` directory.

## Project Highlights

- Flask-based web interface and dashboard
- Gemini-powered command/assistant integration
- Face-authentication workflow using computer-vision libraries
- MySQL database connection layer
- User-scoped command history, AI context, notes, and activation state
- Session management and system-statistics modules

## Tech Stack

Python · Flask · Google GenAI · OpenCV · face-recognition · MySQL

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

Copy `.env.example` to `.env`. Set a unique random `SECRET_KEY` and your MySQL credentials. `GEMINI_API_KEY` enables Gemini responses; without it, local commands can still run but free-form AI answers are unavailable. `WEATHER_API_KEY` is optional and enables weather lookups. Create the MySQL database and tables using `database/schema.sql`. For an existing installation, back up the database and apply `database/migrations/001_user_scoped_history.sql` once before running the updated version; historical rows remain unassigned because their owner cannot be determined safely.

Never commit `.env`, API keys, database passwords, or real biometric data. Use a unique random secret key and disable debug mode in any deployment.

### 5. Run

```bash
python app.py
```

Follow any application-specific setup instructions in [the application README](A.JARVIS/README.md).

## Security and Privacy

This project handles camera input, face-related data, sessions, and API credentials. Use it only with informed consent, protect credentials, and review access controls before exposing it to a network. Face recognition can make mistakes and should not be treated as infallible identity verification.

## Safer Desktop Controls

Shutdown and restart requests now require an exact confirmation within 30 seconds. For example, say `shutdown system`, then `confirm shutdown`. Say `cancel` to cancel the pending action. The application does not execute shutdown or restart commands from the initial phrase alone.

## Automated Tests

GitHub Actions compiles the Python modules and runs the session, memory-persistence, and power-confirmation tests. To run the suite locally from the application directory:

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
