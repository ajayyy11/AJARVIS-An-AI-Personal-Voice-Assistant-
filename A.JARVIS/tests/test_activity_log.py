from datetime import datetime, timezone
from intelligence import activity_log


class FakeCursor:
    def __init__(self, rows=None):
        self.rows=rows or []
        self.executed=[]
        self.closed=False
    def execute(self,sql,params=None): self.executed.append((sql,params))
    def fetchall(self): return self.rows
    def close(self): self.closed=True


class FakeConnection:
    def __init__(self,cursor):
        self.fake_cursor=cursor
        self.committed=False
        self.closed=False
    def cursor(self): return self.fake_cursor
    def commit(self): self.committed=True
    def close(self): self.closed=True


def test_activity_log_persists_metadata_without_arguments_or_outputs(monkeypatch):
    cursor=FakeCursor()
    connection=FakeConnection(cursor)
    monkeypatch.setattr(activity_log,"get_connection",lambda:connection)
    assert activity_log.record_activity(
        username="alice",plan_id="abc",step_number=1,event_type="step_started",
        tool_name="open_website",summary="Open the requested website",
    ) is True
    query,params=cursor.executed[0]
    assert "automation_activity" in query
    assert params==("alice","abc",1,"step_started","open_website","Open the requested website")
    assert connection.committed and cursor.closed and connection.closed
    assert "arguments" not in query.lower() and "result" not in query.lower()


def test_activity_log_is_user_scoped_and_formats_timestamp(monkeypatch):
    stamp=datetime(2026,11,3,tzinfo=timezone.utc)
    cursor=FakeCursor(rows=[(1,"abc",2,"step_completed","get_system_status","Read system status",stamp)])
    connection=FakeConnection(cursor)
    monkeypatch.setattr(activity_log,"get_connection",lambda:connection)
    result=activity_log.list_recent_activity("alice",limit=999)
    assert result[0]["created_at"]==stamp.isoformat()
    assert cursor.executed[0][1]==("alice",100)
    assert "WHERE username = %s" in cursor.executed[0][0]
    assert cursor.closed and connection.closed


def test_activity_log_handles_database_errors_without_crashing(monkeypatch):
    monkeypatch.setattr(activity_log,"get_connection",lambda:(_ for _ in ()).throw(RuntimeError("database unavailable")))
    assert activity_log.record_activity(
        username="alice",plan_id="abc",step_number=None,event_type="plan_created",
        tool_name=None,summary="A plan",
    ) is False
    assert activity_log.list_recent_activity("alice")==[]


def test_workflow_status_is_upserted_with_metadata_not_prompt_or_arguments(monkeypatch):
    cursor = FakeCursor()
    connection = FakeConnection(cursor)
    monkeypatch.setattr(activity_log, "get_connection", lambda: connection)
    assert activity_log.record_activity(
        username="alice",
        plan_id="a" * 32,
        step_number=1,
        event_type="step_started",
        tool_name="get_system_status",
        summary="get_system_status step_started",
        workflow_status="running",
        step_count=3,
        tools_summary="get_system_status, open_website",
    )
    workflow_sql, params = cursor.executed[1]
    assert "automation_workflows" in workflow_sql
    assert "ON DUPLICATE KEY UPDATE" in workflow_sql
    assert params[:5] == (
        "a" * 32, "alice", "running", 3,
        "get_system_status, open_website"
    )
    assert connection.committed


def test_workflow_history_is_scoped_and_interrupted_recovery_uses_process_id(monkeypatch):
    stamp = datetime(2026, 11, 4, tzinfo=timezone.utc)
    cursor = FakeCursor(rows=[
        ("a" * 32, "interrupted", 2, "get_system_status", stamp, stamp, stamp)
    ])
    cursor.rowcount = 2
    connection = FakeConnection(cursor)
    monkeypatch.setattr(activity_log, "get_connection", lambda: connection)
    history = activity_log.list_recent_workflows("alice", limit=200)
    assert history[0]["status"] == "interrupted"
    assert history[0]["created_at"] == stamp.isoformat()
    assert cursor.executed[0][1] == ("alice", 100)

    cursor.executed.clear()
    recovered = activity_log.recover_interrupted_workflows("current-process")
    assert recovered == 2
    query, params = cursor.executed[0]
    assert "status = 'interrupted'" in query
    assert "process_instance_id <> %s" in query
    assert params == ("current-process",)
    assert connection.committed
