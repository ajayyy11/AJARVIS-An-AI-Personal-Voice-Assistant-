# AJARVIS database upgrade runbook

This procedure upgrades an existing AJARVIS database in place. It is designed to preserve registered users and face encodings. Do not drop the database or re-run `schema.sql` against an existing installation.

## 1. Stop AJARVIS and back up MySQL

Close the AJARVIS Flask process first so no new commands are written during the migration.

From Windows Command Prompt (not PowerShell), run the following from a folder where you want the backup stored:

```bat
mysqldump -u root -p --single-transaction --routines --triggers ajarvis_db > ajarvis_backup_before_user_history.sql
```

Replace `root` or `ajarvis_db` if your MySQL account/database uses different names. Check that the dump file exists and is not empty before continuing. Store the backup securely because it contains biometric face encodings and command history.

## 2. Install the updated code and configure it

Update the repository, enter the application folder, activate your virtual environment, and copy `.env.example` to `.env` if you do not already have a configuration file. Keep your real `.env`; do not overwrite it with the example.

Set `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, and `MYSQL_DB` to match the existing database. Keep a unique random `SECRET_KEY`. Do not commit `.env`.

## 3. Check the current schema (read-only)

From inside `A.JARVIS`:

```powershell
python database/verify_schema.py
```

This only reads MySQL metadata and counts unassigned history rows; it does not alter records. If it says the `command_history.username` column is missing, continue to Step 4. If the column already exists, do not blindly run migration 001 again: review the warning and index state first.

## 4. Apply the one-time history migration

From Windows Command Prompt (not PowerShell), run from inside `A.JARVIS`:

```bat
mysql -u root -p ajarvis_db < database\migrations\001_user_scoped_history.sql
```

Adjust the account and database name to match your setup. This migration adds a nullable `username` column and an index. It does not delete or rewrite existing rows. Existing history is left with a NULL owner because its original user cannot be determined safely; the updated app intentionally hides those rows from per-user history and analytics.

## 5. Verify before using the application

Run:

```powershell
python database/verify_schema.py
python -m compileall -q .
pytest -q tests
```

The database preflight should report a usable schema. Warnings about legacy history rows are expected; those rows remain unassigned. If verification fails, do not start using the updated app until the error is resolved.

## Rollback

The safest rollback is to stop the app and restore the verified pre-migration backup to a test database first. Do not drop the new `username` column casually: doing so discards ownership attribution for history created after the migration. Keep the original backup untouched until the upgraded app has been validated.

## Fresh installation

For a brand-new database only, run `database/schema.sql` using a MySQL account allowed to create the database/tables. Change the database name in that script if `MYSQL_DB` is not `ajarvis_db`. Do not use this path as an upgrade method for an existing database.
