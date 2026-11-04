# AJARVIS database upgrade runbook

This procedure upgrades an existing AJARVIS database in place, preserving registered users and face encodings. Do not drop the database or run the fresh-install schema over an existing installation.

## 1. Stop AJARVIS and back up MySQL

Close the AJARVIS Flask process first so no new commands are written during the migration.

From Windows Command Prompt, run:

```bat
mysqldump -u root -p --single-transaction --routines --triggers ajarvis_db > ajarvis_backup_before_phase6.sql
```

Replace the MySQL account and database name if yours differ. Confirm the dump file exists and is not empty. Store it securely because it contains biometric face encodings, command history, and personal preferences/facts.

## 2. Update code and settings

Update the repository and enter the application folder:

```powershell
cd A.JARVIS
```

Keep your existing .env file. Do not replace it with .env.example. Confirm MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, and MYSQL_DB point to the database you intend to upgrade. Keep your unique random SECRET_KEY.

## 3. Preview the migration (read-only)

From inside A.JARVIS, run:

```powershell
python database/migrate_database.py
```

By default this is a dry run. It only reads MySQL metadata and shows planned schema changes. It does not modify records or schema. The Phase 4 `user_memories` table, Phase 5 `automation_activity` table, and Phase 6 workflow/reminder/notification tables are added when missing. Workflow metadata is durable, while detailed action arguments and approval tokens remain in process memory and are discarded on restart. Reminder records and in-app notification state are stored per user.

If it reports missing required tables or columns other than command_history.username, stop and investigate before proceeding. Do not use the migration to repair an unknown schema.

## 4. Apply the migration

After confirming you have a valid backup, run:

```powershell
python database/migrate_database.py --apply
```

Review the planned changes and type MIGRATE only when the displayed database name is correct. The script adds a nullable username column to `command_history` if missing, creates its supporting index if missing, creates the `user_memories` table and its unique `(username, memory_key)` constraint if missing, creates the privacy-minimal `automation_activity` table plus its per-user index if missing, creates the durable `automation_workflows` table, creates opt-in `user_notification_preferences`, and creates `assistant_reminders` and `assistant_notifications` with per-user indexes and notification deduplication. Reminder due times are stored in UTC. Browser notifications are optional; reminders are collected while the local dashboard is open and are surfaced on the next visit if AJARVIS was closed at the due time. Pending approval tokens and sensitive execution arguments are not stored in MySQL. It does not delete or rewrite existing records. Existing history rows remain `username IS NULL` because their original owners cannot be identified safely. The new memory table starts empty and stores each memory under the currently signed-in username.

The script is safe to run again after a successful migration: it should report that no changes are needed. If it reports an error, stop and review the message before attempting manual SQL.

## 5. Verify the database and code

Run:

```powershell
python database/verify_schema.py
python -m compileall -q .
pytest -q tests
```

The schema verifier should report a usable schema. A warning that legacy history rows are unassigned is expected; those rows remain hidden from personal history and analytics.

## Rollback

The safest rollback is to stop the app and restore the verified pre-migration backup to a test database first. Do not drop the new username column casually: doing so would remove ownership attribution for history written after the migration. Do not drop `user_memories` unless you intentionally want to erase every user's saved preferences and facts. Do not drop `automation_activity` unless you intentionally want to erase the automation audit history. Do not drop `automation_workflows` unless you intentionally want to erase durable workflow history. Dropping `assistant_reminders`, `assistant_notifications` or `user_notification_preferences` removes saved reminders, unread alerts and notification choices. Keep the original backup untouched until the upgraded app has been validated.

## Fresh installation

For a brand-new database only, run database/schema.sql using a MySQL account allowed to create the database and tables. Change the database name in the script if MYSQL_DB is not ajarvis_db. Do not use the fresh-install schema as an upgrade method for an existing database.
