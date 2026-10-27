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

4. Copy `.env.example` to `.env` and set the required database credentials, API key, and a strong random Flask secret key.
5. Create/configure the MySQL database using `database/db.py`.
6. Start the app:

   ```bash
   python app.py
   ```

## Security and Privacy

- Keep `.env` out of version control; never publish API keys or database credentials.
- Do not use a predictable fallback secret key in a deployed environment.
- Disable Flask debug mode outside local development and configure secure session-cookie settings.
- Face recognition may produce false matches or rejections. Use informed consent and do not treat it as infallible authentication.

## Main Components

- `app.py` — Flask routes and application entry point
- `config.py` — environment-based configuration
- `database/` — database access
- `intelligence/` — command routing and assistant memory
- `security/` — camera, face-authentication, and session modules
- `system/` — system statistics
- `templates/` and `static/` — web interface

See the repository-level README for the full project overview and setup.
