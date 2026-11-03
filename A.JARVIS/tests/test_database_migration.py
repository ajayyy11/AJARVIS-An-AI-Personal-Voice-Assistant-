from database.migrate_database import plan_migration


def test_legacy_schema_plans_history_and_user_memory_tables():
    tables={"users","command_history"}
    columns={"users":{"username","face_encoding"},"command_history":{"id","command","response"}}
    actions,errors=plan_migration(tables,columns,{"command_history":{}})
    assert actions==["add_nullable_username_column","add_user_history_index","create_user_memories_table"]
    assert errors==[]


def test_already_migrated_schema_has_no_changes():
    tables={"users","command_history","user_memories"}
    columns={
        "users":{"username","face_encoding"},
        "command_history":{"id","username","command","response"},
        "user_memories":{"id","username","memory_key","memory_value","created_at","updated_at"},
    }
    indexes={"command_history":{"idx_command_history_username_id":("username","id")}}
    actions,errors=plan_migration(tables,columns,indexes)
    assert actions==[] and errors==[]


def test_missing_required_table_stops_migration():
    actions,errors=plan_migration(set(),{}, {})
    assert actions==[]
    assert any("Missing required table" in error for error in errors)


def test_missing_core_column_stops_migration():
    tables={"users","command_history"}
    columns={"users":{"username","face_encoding"},"command_history":{"id","command"}}
    actions,errors=plan_migration(tables,columns,{})
    assert actions==[]
    assert any("response" in error for error in errors)


def test_wrong_named_index_stops_migration():
    tables={"users","command_history","user_memories"}
    columns={
        "users":{"username","face_encoding"},
        "command_history":{"id","username","command","response"},
        "user_memories":{"id","username","memory_key","memory_value","created_at","updated_at"},
    }
    indexes={"command_history":{"idx_command_history_username_id":("id","username")}}
    actions,errors=plan_migration(tables,columns,indexes)
    assert actions==[]
    assert any("expected ('username', 'id')" in error for error in errors)


def test_existing_memory_table_with_unknown_schema_stops_migration():
    tables={"users","command_history","user_memories"}
    columns={
        "users":{"username","face_encoding"},
        "command_history":{"id","username","command","response"},
        "user_memories":{"id","username","memory_key"},
    }
    indexes={"command_history":{"idx_command_history_username_id":("username","id")}}
    actions,errors=plan_migration(tables,columns,indexes)
    assert actions==[]
    assert any("user_memories is missing" in error for error in errors)
