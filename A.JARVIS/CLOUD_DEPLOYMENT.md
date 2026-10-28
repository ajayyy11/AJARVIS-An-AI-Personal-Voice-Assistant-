# AJARVIS Cloud Deployment Guide

This guide deploys the separate hosted workspace entry point. It deliberately does **not** start the local webcam/face-recognition pipeline or expose Windows desktop-control handlers.

## Cloud features

- Password-based account creation and login with hashed passwords, session timeout, CSRF tokens, and login-attempt throttling
- User-scoped PostgreSQL notes, assistant history, tasks, reminders, and uploaded-document text
- Gemini assistant with an explicit read-only tool allow-list
- Separate Google Search-grounded research responses with source links when available
- PDF, DOCX, XLSX, CSV, and TXT extraction with bounded size/row/page/text limits and document Q&A
- In-page/browser reminders while the user has the workspace open
- Responsive dashboard, text chat, browser speech input and optional speech output
- /healthz process health and /readyz database readiness endpoints
- Per-user deletion for notes/tasks/documents and a password-confirmed account/data deletion endpoint

Cloud computer access is intentionally disabled. Running the app on a cloud host cannot give it access to a visitor's personal webcam, files, applications, or Windows power controls. Those capabilities need a separately installed local agent and an explicit approval/secure pairing design.

## Deploy on Render

The repository root contains render.yaml. The Blueprint defines one Python web service and a PostgreSQL database in Singapore. The service uses A.JARVIS/requirements-web.txt and starts cloud_app:app.

1. Review and merge the AJARVIS cloud release pull request into main. Render must be able to read the merged render.yaml.
2. Open the Render Blueprint creation link for this repository:

   https://dashboard.render.com/blueprint/new?repo=https://github.com/ajayyy11/AJARVIS-An-AI-Personal-Voice-Assistant-

3. Review the resources before clicking **Apply**. The web service uses Render's Free plan and can sleep after inactivity. The PostgreSQL configuration uses the small paid 0.1c-256mb plan and 1 GB storage so app data is not on the ephemeral web filesystem. Render's displayed price at apply time is authoritative; current pricing references a $6/month compute tier for 0.1c-256mb and $0.30/GB for database storage. This blueprint is not a zero-cost production deployment.
4. When prompted, set GEMINI_API_KEY in Render's environment-variable settings. Never put API keys in Git or in this file. GEMINI_MODEL and GEMINI_WEB_MODEL default to gemini-2.5-flash.
5. Apply the Blueprint and wait for the first deploy to complete.
6. Open the resulting https://...onrender.com/readyz. It should return JSON with "status": "ready" and "database": "ok".
7. Open the service root, create an account, test notes/tasks/document upload, and try a grounded web query. Test one account with two different users to verify their notes, tasks and documents are isolated.

## Environment configuration

Render supplies DATABASE_URL from the managed database and SECRET_KEY from a generated secret. The service uses HTTPS-only session cookies in cloud mode. Set GEMINI_API_KEY in the dashboard; no API key is stored in this repository.

For a local development run, set SECRET_KEY, install the cloud dependencies, and point DATABASE_URL at a PostgreSQL development database:

```bash
cd A.JARVIS
python -m pip install -r requirements-web.txt
# Configure SECRET_KEY and DATABASE_URL in a local, untracked .env file.
python cloud_app.py
```

Run tests from this directory with:

```bash
pytest -q tests
```

## Important operational notes

- The database schema is created idempotently on the first non-health request. /readyz checks storage connectivity and schema initialization.
- Free Render web services can spin down and local filesystem changes are lost on spin-down or redeploy; user data is kept in PostgreSQL instead. Free Postgres is not used by this Blueprint because Render documents that it expires after 30 days.
- Browser reminders are checked while the dashboard is open; there is no delivery to a closed browser or offline device. Browser notification permission is optional.
- Document text extracted from uploads is stored in the database so it survives redeploys. Deleting a document removes the extracted text from AJARVIS's database. The original file bytes are not retained.
- Scanned PDFs without a text layer report that no readable text was found. OCR is not part of this cloud build.
- Note content or document extracts may be sent to Gemini when you ask the assistant to search or analyze them. Do not upload confidential company documents or store secrets unless your organization's policies and the configured provider account permit that processing.
- The hosted app can use the Gemini API and Google Search grounding; API usage is subject to the provider's terms and billing.
- This is a hobby deployment starting point, not a security certification. Before public/enterprise use, add a production-grade distributed rate limiter, email verification and account recovery, backups/restore drills, dependency scanning, and further abuse/rate controls. Review data-retention, privacy and biometric policies before enabling any biometric feature in a separate local deployment.
