# AJARVIS Cloud: zero-cost deployment

This setup is for a hobby/demo deployment with **no required monthly hosting or database subscription**. Free tiers have quotas, can sleep, and may change; they are not production SLAs.

## Free stack

- Render Free Web Service for the Flask/Gunicorn app.
- Neon Free PostgreSQL for persistent account and app data. Create a Neon project and copy its pooled PostgreSQL connection string.
- Gemini API using a Google AI Studio free-tier key, only if your account/model has free quota. Rate limits and model availability apply; never enable paid billing if your budget is zero.
- GitHub for source control and automatic deployments.

## Deploy

1. Open the repository pull request and merge the reviewed changes to `main`.
2. Create a Neon project on its Free plan. Create a database/user if needed and copy the connection string. Keep it private.
3. In Render, choose **New → Blueprint** and connect this repository. Select the `main` branch and apply the root `render.yaml`. The Blueprint creates only the free web service; it does not create a paid Render database.
4. In the Render service's Environment settings, set:
   - `DATABASE_URL`: Neon PostgreSQL connection string. Use the provider's pooled connection string if available.
   - `GEMINI_API_KEY`: your Google AI Studio API key. Keep it server-side; never put it in HTML or JavaScript.
   - `SECRET_KEY`: Render generates this automatically.
5. Deploy and wait for the build. Check `/healthz` and `/readyz`; then create a test account and verify notes, preferences, tasks, documents, and logout.
6. Keep an export/backup of anything important. A free service is suitable for demos, not critical or confidential data.

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
