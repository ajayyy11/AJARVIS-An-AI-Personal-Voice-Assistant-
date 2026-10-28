# AJARVIS Cloud: zero-cost deployment

This setup is for a hobby/demo deployment with **no required monthly hosting or database subscription**. Free tiers have quotas, can sleep, and may change; they are not production SLAs.

## Free stack

- Render Free Web Service for the Flask/Gunicorn app.
- Neon Free PostgreSQL for persistent account and app data. Create a Neon project and copy its pooled PostgreSQL connection string.
- Gemini API using a Google AI Studio free-tier key, only if your account/model has free quota. Rate limits and model availability apply; never enable paid billing if your budget is zero.
- GitHub for source control and automatic deployments.

## Current deployment

The cloud workspace is deployed at https://ajarvis-cloud.onrender.com. The Render service is configured on the Free plan, and its `DATABASE_URL` should point to the Neon PostgreSQL database. This guide also documents how to reproduce the setup if you need to redeploy.

## Deploy or redeploy

1. Use the repository's `main` branch, where the cloud deployment changes are merged.
2. Create a Neon project on its Free plan if you do not already have one. Create a database/user if needed and copy the connection string. Keep it private.
3. In Render, choose **New → Blueprint** and connect this repository. Select the `main` branch and apply the root `render.yaml`. The Blueprint creates only the free web service; it does not create a paid Render database.
4. In the Render service's Environment settings, set:
   - `DATABASE_URL`: Neon PostgreSQL connection string. Use the provider's pooled connection string if available.
   - `GEMINI_API_KEY`: your Google AI Studio API key. Keep it server-side; never put it in HTML or JavaScript.
   - `SECRET_KEY`: Render generates this automatically.
5. Deploy and wait for the build. Check `/healthz` and `/readyz`; then create a test account and verify notes, preferences, tasks, documents, and logout.
6. Keep an export/backup of anything important. A free service is suitable for demos, not critical or confidential data.

## Voice interaction

- In the cloud workspace, press the microphone button to begin a voice session. The browser handles speech recognition; select English (India), English (US), Tamil, or Hindi in the Voice Language control.
- AJARVIS accepts a leading “Hey Jarvis” phrase after the microphone has been pressed. This is not an always-on wake word: browsers do not guarantee continuous background listening for hosted websites.
- Spoken replies can be muted or stopped from the voice controls. Voice recognition and voice playback depend on the browser, device, selected language, microphone permission, and available system voices.
- Simple spoken commands include saving/reading notes and adding/listing tasks. “Remind me to …” creates a task but does not schedule a timed reminder unless a date/time is set in Tasks & Reminders.

## Free-tier trade-offs

- Render Free web services spin down after inactivity and can take around a minute to wake up. Their filesystem is ephemeral, so the database must remain external.
- Neon Free currently lists 100 compute-hours per project per month, 1 GB database storage per project, and 5 GB public network transfer per project. If quotas are reached, database access may pause until the quota resets or plan changes.
- Gemini API free quotas vary by model, account and region. If no free quota is available, AI calls will fail until a free-eligible model/quota is available. Do not add a payment method or enable paid billing if you must stay at ₹0.
- Free tier limits/pricing can change. Verify provider dashboards before creating resources.
- Do not store passwords, API keys, confidential company documents, or sensitive data in notes/preferences. Content you ask the assistant to analyze may be sent to Gemini.

## Troubleshooting

- `/healthz` should return a basic healthy response.
- `/readyz` checks app readiness and database connectivity.
- If readiness fails, inspect Render logs and verify that `DATABASE_URL` is a PostgreSQL URL, correctly copied and URL-encoded where required.
- If AI chat fails, verify `GEMINI_API_KEY`, free-tier eligibility and model availability.
- If the app wakes slowly, wait for the Render instance to start; free services sleep after inactivity.
