import pytest

import intelligence.notes as notes


def test_notes_are_isolated_between_usernames(monkeypatch, tmp_path):
    monkeypatch.setattr(notes, "NOTES_DIRECTORY", tmp_path)

    alice_path = notes.notes_path("alice")
    bob_path = notes.notes_path("bob")
    alice_path.write_text(
        "[2026-10-28 09:00] Vessel IT checklist\n"
        "[2026-10-28 09:10] Ask about router settings\n",
        encoding="utf-8",
    )
    bob_path.write_text("[2026-10-28 10:00] Private Bob note\n", encoding="utf-8")

    assert notes.read_recent_notes("alice", limit=5) == [
        "[2026-10-28 09:00] Vessel IT checklist",
        "[2026-10-28 09:10] Ask about router settings",
    ]
    assert "Private Bob note" not in notes.read_recent_notes("alice", limit=5)


def test_note_search_is_case_insensitive_and_newest_first(monkeypatch, tmp_path):
    monkeypatch.setattr(notes, "NOTES_DIRECTORY", tmp_path)
    path = notes.notes_path("alice")
    path.write_text(
        "[2026-10-28 09:00] Old meeting with engineering\n"
        "[2026-10-28 09:10] Another reminder\n"
        "[2026-10-28 09:20] Meeting with the captain\n",
        encoding="utf-8",
    )

    assert notes.search_personal_notes("alice", "MEETING", limit=2) == [
        "[2026-10-28 09:20] Meeting with the captain",
        "[2026-10-28 09:00] Old meeting with engineering",
    ]


def test_notes_reader_handles_missing_file_and_validates_limits(monkeypatch, tmp_path):
    monkeypatch.setattr(notes, "NOTES_DIRECTORY", tmp_path)

    assert notes.read_recent_notes("new-user") == []
    with pytest.raises(ValueError, match="limit"):
        notes.read_recent_notes("new-user", limit=0)
    with pytest.raises(ValueError, match="query"):
        notes.search_personal_notes("new-user", " ")
