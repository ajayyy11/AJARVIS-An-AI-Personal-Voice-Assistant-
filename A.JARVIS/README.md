# A.J.A.R.V.I.S. — AI Personal Assistant

A local Windows-focused assistant application using Flask, Google Gemini integration, MySQL, and face-authentication components.

## Features

- Flask web interface with login, registration, and dashboard pages
- Gemini-backed assistant/command integration
- Face-authentication and camera-streaming components
- MySQL persistence and command/memory-related modules
- System resource statistics

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
5. For a new database, create the tables using `database/schema.sql`. To safely upgrade an existing database while preserving users and face encodings, follow [the database upgrade runbook](database/migrations/README.md) before starting the updated app.
6. Start the app:

   ```bash
   python app.py
   ```

## Safer Desktop Controls

Shutdown and restart requests need an exact confirmation within 30 seconds: say `shutdown system`, then `confirm shutdown`. Say `cancel` to cancel. The initial request alone does not execute the action.

## Automated Tests

From this directory, set `SECRET_KEY` and run `python -m pip install Flask python-dotenv pytest mysql-connector-python`, followed by `pytest -q tests`. GitHub Actions also checks the dashboard's inline JavaScript syntax and compiles the Python modules.

## User-Scoped History

Command history, AI context, analytics, notes, and activation state are scoped to the authenticated username. The current schema stores each new history entry with its username; legacy rows remain unassigned after migration so they are not exposed to another account.

## Security and Privacy

- Keep `.env` out of version control; never publish API keys or database credentials.
- Do not use a predictable fallback secret key in a deployed environment.
- Disable Flask debug mode outside local development and configure secure session-cookie settings.
- Face recognition may produce false matches or rejections and this project does not implement liveness detection. Use informed consent and do not treat face recognition alone as infallible identity verification. `FACE_MATCH_THRESHOLD` defaults to 0.55; lower values are stricter, and the threshold must be validated with consented samples under the target camera and lighting conditions.

## Main Components

- `app.py` — Flask routes and application entry point
- `config.py` — environment-based configuration
- `database/` — database access
- `intelligence/` — command routing and assistant memory
- `security/` — camera, face-authentication, and session modules
- `system/` — system statistics
- `templates/` and `static/` — web interface

See the repository-level README for the full project overview and setup.
