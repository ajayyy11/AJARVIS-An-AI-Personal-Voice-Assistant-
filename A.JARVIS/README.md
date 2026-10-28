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


## Tool-Enabled Agent Foundation

The AI fallback now uses manual Gemini function calling through an explicit allow-list in `intelligence/tool_registry.py` and `intelligence/agent.py`.

The initial agent can read the current date/time, CPU and memory usage, home-disk usage, battery status, and the signed-in user's saved notes (recent notes or phrase search). Calls are validated against registered argument schemas, and the agent limits the number of tool calls and the amount of returned data. Automatic SDK function execution is disabled so the application, not the model, decides whether a requested tool can run.

Only read-only tools are automatically eligible. Unknown tools, invalid arguments, and tools marked as side-effecting or destructive are rejected. When the note tools are used, matching note content is sent to the configured Gemini model for an answer; do not store passwords, API keys, or other secrets in notes or personalization preferences. The model cannot execute arbitrary Python, shell commands, or file paths through this interface. General desktop automation remains disabled until a trusted approval flow is implemented and tested.

Requests containing wording such as `search the web`, `latest`, `current`, or `recent` are routed through `intelligence/web_research.py`, a separate Google Search-grounded Gemini request. The response includes up to five validated HTTP(S) source links when grounding metadata is available. This requires `GEMINI_API_KEY`; the default model is `gemini-2.5-flash`, and `GEMINI_WEB_MODEL` can override it. Gemini API usage charges may apply. When no source metadata is returned, AJARVIS says it could not verify source links.

Run the focused unit tests with:

```bash
pytest -q tests/test_tool_registry.py tests/test_agent.py tests/test_notes.py tests/test_web_research.py
```



## Hosted Cloud Mode

Use cloud_app.py and requirements-web.txt for the Render-hosted workspace. The cloud version uses password accounts and PostgreSQL storage for notes, editable user preferences, tasks, reminders, document text, and history. Personal preferences are visible and removable from the dashboard. The Agent Activity panel records executed tool names, outcome and duration without recording tool arguments or private note/document contents. It does not import the camera or Windows desktop-control entry points used by app.py. Deployment is configured by the repository-root render.yaml file.

See [CLOUD_DEPLOYMENT.md](CLOUD_DEPLOYMENT.md) before applying the Blueprint, especially its current cost, ephemeral service, Gemini API, and data-retention notes.
