from database.migrate_database import plan_migration


def test_legacy_schema_plans_only_username_column_and_index():
    tables = {"users", "command_history"}
    columns = {
        "users": {"username", "face_encoding"},
        "command_history": {"id", "command", "response"},
    }
    indexes = {"command_history": {}}

    actions, errors = plan_migration(tables, columns, indexes)

    assert actions == ["add_nullable_username_column", "add_user_history_index"]
    assert errors == []


def test_already_migrated_schema_has_no_changes():
    tables = {"users", "command_history"}
    columns = {
        "users": {"username", "face_encoding"},
        "command_history": {"id", "username", "command", "response"},
    }
    indexes = {"command_history": {"idx_command_history_username_id": ("username", "id")}}

    actions, errors = plan_migration(tables, columns, indexes)

    assert actions == []
    assert errors == []


def test_missing_required_table_stops_migration():
    actions, errors = plan_migration(set(), {}, {})

    assert actions == []
    assert any("Missing required table" in error for error in errors)


def test_missing_core_column_stops_migration():
    tables = {"users", "command_history"}
    columns = {
        "users": {"username", "face_encoding"},
        "command_history": {"id", "command"},
    }

    actions, errors = plan_migration(tables, columns, {})

    assert actions == []
    assert any("response" in error for error in errors)


def test_wrong_named_index_stops_migration():
    tables = {"users", "command_history"}
    columns = {
        "users": {"username", "face_encoding"},
        "command_history": {"id", "username", "command", "response"},
    }
    indexes = {"command_history": {"idx_command_history_username_id": ("id", "username")}}

    actions, errors = plan_migration(tables, columns, indexes)

    assert actions == []
    assert any("expected ('username', 'id')" in error for error in errors)
