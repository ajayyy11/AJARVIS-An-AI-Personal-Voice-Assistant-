from datetime import datetime, timezone
import pytest
from intelligence import user_memory


class FakeCursor:
    def __init__(self, fetchone=None, fetchall=None, rowcount=1):
        self.fetchone_value=fetchone
        self.fetchall_value=fetchall or []
        self.rowcount=rowcount
        self.executed=[]
        self.closed=False
    def execute(self,sql,params=None):
        self.executed.append((sql,params))
    def fetchone(self):
        value=self.fetchone_value
        self.fetchone_value=None
        return value
    def fetchall(self): return self.fetchall_value
    def close(self): self.closed=True


class FakeConnection:
    def __init__(self,cursor):
        self.cursor_value=cursor
        self.committed=False
        self.rolled_back=False
        self.closed=False
    def cursor(self): return self.cursor_value
    def commit(self): self.committed=True
    def rollback(self): self.rolled_back=True
    def close(self): self.closed=True


def test_save_memory_inserts_user_scoped_record(monkeypatch):
    cursor=FakeCursor(fetchone=None)
    connection=FakeConnection(cursor)
    monkeypatch.setattr(user_memory,"get_connection",lambda:connection)
    result=user_memory.save_memory("alice","Answer Style","Use concise examples")
    assert result=={"key":"answer_style","value":"Use concise examples"}
    assert cursor.executed[0][1]==("alice","answer_style")
    assert cursor.executed[1][1]==("alice","answer_style","Use concise examples")
    assert connection.committed and cursor.closed and connection.closed


def test_save_memory_updates_existing_record(monkeypatch):
    cursor=FakeCursor(fetchone=(7,))
    connection=FakeConnection(cursor)
    monkeypatch.setattr(user_memory,"get_connection",lambda:connection)
    result=user_memory.save_memory("alice","answer_style","Detailed")
    assert result["value"]=="Detailed"
    assert len(cursor.executed)==2
    assert cursor.executed[1][1]==("Detailed","alice","answer_style")
    assert connection.committed


def test_list_memories_only_reads_current_user_and_bounds_limit(monkeypatch):
    timestamp=datetime(2026,11,3,tzinfo=timezone.utc)
    cursor=FakeCursor(fetchall=[("answer_style","Concise",timestamp)])
    connection=FakeConnection(cursor)
    monkeypatch.setattr(user_memory,"get_connection",lambda:connection)
    result=user_memory.list_memories("alice",limit=999)
    assert result==[{"key":"answer_style","value":"Concise","updated_at":timestamp.isoformat()}]
    assert cursor.executed[0][1]==("alice",user_memory.MAX_MEMORIES)


def test_delete_memory_is_scoped_to_the_current_user(monkeypatch):
    cursor=FakeCursor(rowcount=1)
    connection=FakeConnection(cursor)
    monkeypatch.setattr(user_memory,"get_connection",lambda:connection)
    assert user_memory.delete_memory("alice","answer_style") is True
    assert cursor.executed[0][1]==("alice","answer_style")
    assert connection.committed


def test_remember_fact_has_a_stable_deterministic_key(monkeypatch):
    saved=[]
    monkeypatch.setattr(user_memory,"save_memory",lambda username,key,value:saved.append((username,key,value)) or {"key":key,"value":value})
    a=user_memory.remember_fact("alice","I prefer examples")
    b=user_memory.remember_fact("alice","I prefer examples")
    assert a==b
    assert saved[0][1].startswith("fact_")
    assert saved[0][2]=="I prefer examples"


def test_forget_matching_memory_only_deletes_matching_owned_entries(monkeypatch):
    deleted=[]
    monkeypatch.setattr(user_memory,"list_memories",lambda username:[
        {"key":"answer_style","value":"Concise replies"},
        {"key":"work_context","value":"Vessel IT support"},
    ])
    monkeypatch.setattr(user_memory,"delete_memory",lambda username,key:deleted.append((username,key)) or True)
    assert user_memory.forget_matching_memory("alice","concise")==1
    assert deleted==[("alice","answer_style")]


@pytest.mark.parametrize("key",["","A","../secret","x"*81])
def test_invalid_memory_keys_are_rejected(key):
    with pytest.raises(ValueError):
        user_memory.normalize_memory_key(key)


@pytest.mark.parametrize("value",["","   ","x"*1001,"my password is secret","the API key is abc"])
def test_invalid_or_sensitive_memory_values_are_rejected(value):
    with pytest.raises(ValueError):
        user_memory.validate_memory_value(value)


def test_memory_is_scoped_and_requires_valid_user():
    with pytest.raises(ValueError):
        user_memory.save_memory(" ","answer_style","Concise")


def test_memory_key_normalizes_spaces_to_underscores():
    assert user_memory.normalize_memory_key("Answer Style")=="answer_style"
