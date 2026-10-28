# AJARVIS 2.0 — Agent Roadmap

This roadmap keeps the existing Windows assistant working while adding broader capabilities in reviewable phases. This is a plan, not a claim that all features below already exist.

## Current foundation

- Manual Gemini function calling through a local allow-list
- Runtime argument validation for registered tools
- Explicit risk levels and confirmation metadata
- Read-only starter tools for date/time, system usage, battery status, and per-user note search
- Separate Google Search-grounded Gemini research responses with validated source links
- Bounded tool-call rounds and output length
- Automated tests for unknown tools, invalid arguments, and side-effect blocking

## Phase 1 — Agent reliability and safety

- Expand tests around tool schemas, timeouts, provider errors, and session boundaries.
- Add an audit trail for tool name, timestamp, outcome, and user, without logging sensitive arguments or secrets.
- Create a real user-facing approval flow with short-lived, user-scoped approvals for each specific action.
- Keep the model unable to approve its own proposed actions.
- Add CI checks for dependencies and a minimal integration test for the agent adapter.

## Phase 2 — Personal memory and productivity

- Add editable, user-scoped preferences and facts with user-visible review and deletion.
- Build tasks, reminders, and recurring reminders with timezone-safe scheduling.
- Ensure data access is limited to the authenticated user and provide retention controls.

## Phase 3 — Document and web intelligence

- Add safe file selection and upload flows for PDFs, Word files, and spreadsheets.
- Extract and summarize documents, cite page/sheet locations, and distinguish extracted facts from model inference.
- Extend grounded web research with explicit timeout budgets, source-quality hints, and integration tests for provider failures.
- Do not allow retrieved document/web instructions to override system safety rules.

## Phase 4 — Voice and interface

- Improve listening/ speaking states, interruption and retry behavior, and accessible text interaction.
- Show which tools were used and when an approval is needed.
- Offer a tool activity timeline and meaningful status/error feedback.

## Phase 5 — Approved desktop automation

- Add narrow, purpose-built tools rather than general-purpose shell access.
- Require visible approval for file modification, sending messages, changing settings, and power actions.
- Add path restrictions, preview/dry-run, rollback where possible, and detailed tests before enabling each capability.

## Phase 6 — Offline operation and quality

- Identify which local features can work without internet or API credentials.
- Add latency, tool success, rejection, and failure metrics without storing private prompt content.
- Build an evaluation set for correctness, safe refusal, tool selection, and regression testing.

## Release principle

A feature is not considered complete until its behavior is documented, user-scoped, tested, and integrated in a way that avoids unintended side effects. Face recognition should remain a convenience feature rather than the sole security boundary.
