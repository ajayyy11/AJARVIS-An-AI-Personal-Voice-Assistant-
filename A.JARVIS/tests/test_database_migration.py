
TABLE_COLUMNS = {
    "users": {"username", "face_encoding"},
    "command_history": {"id", "username", "command", "response"},
    "user_memories": {"id", "username", "memory_key", "memory_value", "created_at", "updated_at"},
    "automation_activity": {"id", "username", "plan_id", "step_number", "event_type", "tool_name", "summary", "created_at"},
    "automation_workflows": {"plan_id", "username", "status", "step_count", "tools_summary", "process_instance_id", "created_at", "updated_at", "finished_at"},
    "user_notification_preferences": {"username", "reminders_enabled", "browser_notifications_enabled", "updated_at"},
    "assistant_reminders": {"id", "username", "title", "due_at", "status", "created_at", "updated_at", "completed_at"},
    "assistant_notifications": {"id", "username", "reminder_id", "title", "body", "created_at", "presented_at", "read_at"},
    "assistant_projects": {"id", "username", "name", "objective", "status", "created_at", "updated_at"},
    "assistant_tasks": {"id", "username", "project_id", "title", "details", "priority", "due_at", "effort_minutes", "status", "created_at", "updated_at", "completed_at"},
}
TABLE_INDEXES = {
    "users": {"uq_users_username": ("username",)},
    "command_history": {"idx_command_history_username_id": ("username", "id")},
    "user_memories": {"uq_user_memories_username_key": ("username", "memory_key")},
    "automation_activity": {"idx_automation_activity_user_id": ("username", "id")},
    "automation_workflows": {"idx_automation_workflows_user_updated": ("username", "updated_at")},
    "assistant_reminders": {"idx_assistant_reminders_user_status_due": ("username", "status", "due_at")},
    "assistant_notifications": {
        "uq_assistant_notifications_user_reminder": ("username", "reminder_id"),
        "idx_assistant_notifications_user_read": ("username", "read_at", "id"),
    },
    "assistant_projects": {"idx_assistant_projects_user_status_updated": ("username", "status", "updated_at")},
    "assistant_tasks": {"idx_assistant_tasks_user_status_due": ("username", "status", "due_at")},
}


def full_schema():
    return (
        set(TABLE_COLUMNS),
        {name: set(columns) for name, columns in TABLE_COLUMNS.items()},
        {name: dict(indexes) for name, indexes in TABLE_INDEXES.items()},
    )


def test_legacy_schema_plans_all_missing_phase_tables_and_history_index():
    from database.migrate_database import plan_migration

    tables = {"users", "command_history"}
    columns = {
        "users": {"username", "face_encoding"},
        "command_history": {"id", "command", "response"},
    }
    actions, errors = plan_migration(tables, columns, {"command_history": {}})
    assert errors == []
    assert set(actions) == {
        "add_nullable_username_column",
        "add_user_history_index",
        "create_user_memories_table",
        "create_automation_activity_table",
        "create_automation_workflows_table",
        "create_user_notification_preferences_table",
        "create_assistant_reminders_table",
        "create_assistant_notifications_table",
        "create_assistant_projects_table",
        "create_assistant_tasks_table",
    }


def test_already_migrated_schema_has_no_changes():
    from database.migrate_database import plan_migration

    actions, errors = plan_migration(*full_schema())
    assert actions == []
    assert errors == []


def test_missing_required_core_table_stops_migration():
    from database.migrate_database import plan_migration

    actions, errors = plan_migration(set(), {}, {})
    assert actions == []
    assert any("Missing required table" in error for error in errors)


def test_missing_core_column_stops_migration():
    from database.migrate_database import plan_migration

    tables, columns, indexes = full_schema()
    columns["command_history"].remove("response")
    actions, errors = plan_migration(tables, columns, indexes)
    assert actions == []
    assert any("response" in error for error in errors)


def test_wrong_history_index_is_rejected_without_planning_changes():
    from database.migrate_database import plan_migration

    tables, columns, indexes = full_schema()
    indexes["command_history"]["idx_command_history_username_id"] = ("id", "username")
    actions, errors = plan_migration(tables, columns, indexes)
    assert actions == []
    assert any("expected ('username', 'id')" in error for error in errors)


def test_existing_memory_table_with_unknown_schema_stops_migration():
    from database.migrate_database import plan_migration

    tables, columns, indexes = full_schema()
    columns["user_memories"].remove("memory_value")
    actions, errors = plan_migration(tables, columns, indexes)
    assert actions == []
    assert any("user_memories is missing" in error for error in errors)


def test_existing_user_memory_table_without_unique_owner_key_is_rejected():
    from database.migrate_database import plan_migration

    tables, columns, indexes = full_schema()
    indexes["user_memories"].pop("uq_user_memories_username_key")
    actions, errors = plan_migration(tables, columns, indexes)
    assert actions == []
    assert any("unique index uq_user_memories_username_key" in error for error in errors)


def test_missing_automation_activity_index_plans_index_only():
    from database.migrate_database import plan_migration

    tables, columns, indexes = full_schema()
    indexes["automation_activity"].pop("idx_automation_activity_user_id")
    actions, errors = plan_migration(tables, columns, indexes)
    assert actions == ["add_automation_activity_index"]
    assert errors == []


def test_phase6_existing_tables_missing_indexes_plan_only_safe_indexes():
    from database.migrate_database import plan_migration

    tables, columns, indexes = full_schema()
    indexes["assistant_reminders"].pop("idx_assistant_reminders_user_status_due")
    indexes["automation_workflows"].pop("idx_automation_workflows_user_updated")
    actions, errors = plan_migration(tables, columns, indexes)
    assert set(actions) == {
        "add_assistant_reminders_index",
        "add_automation_workflows_index",
    }
    assert errors == []


def test_phase6_wrong_notification_unique_index_is_rejected():
    from database.migrate_database import plan_migration

    tables, columns, indexes = full_schema()
    indexes["assistant_notifications"]["uq_assistant_notifications_user_reminder"] = ("reminder_id", "username")
    actions, errors = plan_migration(tables, columns, indexes)
    assert actions == []
    assert any("must cover (username, reminder_id)" in error for error in errors)


def test_existing_phase6_table_with_missing_columns_is_rejected():
    from database.migrate_database import plan_migration

    tables, columns, indexes = full_schema()
    columns["assistant_reminders"].remove("due_at")
    actions, errors = plan_migration(tables, columns, indexes)
    assert actions == []
    assert any("assistant_reminders is missing" in error for error in errors)


def test_phase7_missing_project_task_indexes_are_planned():
    from database.migrate_database import plan_migration

    tables, columns, indexes = full_schema()
    indexes["assistant_projects"].pop("idx_assistant_projects_user_status_updated")
    indexes["assistant_tasks"].pop("idx_assistant_tasks_user_status_due")
    actions, errors = plan_migration(tables, columns, indexes)
    assert set(actions) == {"add_assistant_projects_index", "add_assistant_tasks_index"}
    assert errors == []


def test_phase7_incompatible_task_schema_is_rejected():
    from database.migrate_database import plan_migration

    tables, columns, indexes = full_schema()
    columns["assistant_tasks"].remove("priority")
    actions, errors = plan_migration(tables, columns, indexes)
    assert actions == []
    assert any("assistant_tasks is missing" in error for error in errors)
