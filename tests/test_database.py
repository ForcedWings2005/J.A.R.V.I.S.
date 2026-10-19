"""Tests for the schema migrations in database.py.

Each test uses its own in-memory database, not the shared one.
"""
import sqlite3

import pytest

import database

LATEST = len(database.MIGRATIONS)


def columns(c, table):
    return {r[1] for r in c.execute(f"PRAGMA table_info({table})")}


def test_new_database_gets_every_table():
    c = sqlite3.connect(":memory:")
    assert database.migrate(c) == LATEST
    assert {"id", "title", "date", "time", "end_time", "repeat_rule",
            "repeat_until", "repeat_days"} <= columns(c, "events")
    assert {"id", "title", "due", "done"} <= columns(c, "tasks")
    assert {"event_id", "date"} <= columns(c, "event_exceptions")


def test_migrating_twice_changes_nothing():
    c = sqlite3.connect(":memory:")
    database.migrate(c)
    before = c.execute("SELECT sql FROM sqlite_master ORDER BY name").fetchall()
    assert database.migrate(c) == LATEST
    assert c.execute("SELECT sql FROM sqlite_master ORDER BY name").fetchall() == before


def test_first_version_database_keeps_its_events():
    """A database from before durations and repeats existed."""
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, "
              "title TEXT NOT NULL, date TEXT NOT NULL, time TEXT NOT NULL)")
    c.execute("INSERT INTO events (title, date, time) VALUES ('Dentist', '2030-01-08', '15:00')")
    c.commit()
    database.migrate(c)
    row = c.execute("SELECT title, time, end_time, repeat_rule FROM events").fetchone()
    assert row == ("Dentist", "15:00", None, "none")


def test_database_from_before_versioning_is_adopted():
    """The real jarvis.db: every column already added by the old code, but version 0."""
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, "
              "title TEXT NOT NULL, date TEXT NOT NULL, time TEXT NOT NULL, end_time TEXT, "
              "repeat_rule TEXT NOT NULL DEFAULT 'none', repeat_until TEXT, repeat_days TEXT)")
    c.execute("CREATE TABLE event_exceptions (event_id INTEGER NOT NULL, date TEXT NOT NULL, "
              "PRIMARY KEY (event_id, date))")
    c.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, "
              "title TEXT NOT NULL, due TEXT, done INTEGER NOT NULL DEFAULT 0)")
    c.execute("INSERT INTO events (title, date, time, repeat_rule, repeat_days) "
              "VALUES ('Class', '2030-01-09', '09:00', 'weekly', '2,4')")
    c.execute("INSERT INTO tasks (title) VALUES ('Buy milk')")
    c.commit()
    assert database.version(c) == 0
    assert database.migrate(c) == LATEST
    assert c.execute("SELECT title, repeat_days FROM events").fetchall() == [("Class", "2,4")]
    assert c.execute("SELECT title FROM tasks").fetchall() == [("Buy milk",)]


def test_a_failing_step_is_rolled_back(monkeypatch):
    def broken(c):
        c.execute("CREATE TABLE half_done (x)")
        raise RuntimeError("boom")

    c = sqlite3.connect(":memory:")
    database.migrate(c)
    monkeypatch.setattr(database, "MIGRATIONS", [*database.MIGRATIONS, broken])
    with pytest.raises(RuntimeError):
        database.migrate(c)
    assert database.version(c) == LATEST
    tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master")}
    assert "half_done" not in tables


def test_newer_database_than_the_code_is_refused():
    c = sqlite3.connect(":memory:")
    c.execute(f"PRAGMA user_version = {LATEST + 1}")
    with pytest.raises(RuntimeError, match="newer than this code"):
        database.migrate(c)


# --- Step 3: notes (full-text search) --------------------------------------------------

def test_new_database_has_a_searchable_notes_table():
    c = sqlite3.connect(":memory:")
    database.migrate(c)
    c.execute("INSERT INTO notes (text, created) VALUES ('Favourite food is sushi', '2030-01-07')")
    found = c.execute("SELECT text FROM notes WHERE notes MATCH 'sushi'").fetchall()
    assert found == [("Favourite food is sushi",)]


def test_version_2_database_keeps_its_data_and_gains_notes(monkeypatch):
    """The real jarvis.db today: version 2, with events and tasks in it."""
    c = sqlite3.connect(":memory:")
    monkeypatch.setattr(database, "MIGRATIONS", database.MIGRATIONS[:2])
    database.migrate(c)
    c.execute("INSERT INTO events (title, date, time) VALUES ('Dentist', '2030-01-08', '15:00')")
    c.execute("INSERT INTO tasks (title) VALUES ('Buy milk')")
    c.commit()
    monkeypatch.undo()

    assert database.version(c) == 2
    assert database.migrate(c) == LATEST
    assert c.execute("SELECT title FROM events").fetchall() == [("Dentist",)]
    assert c.execute("SELECT title FROM tasks").fetchall() == [("Buy milk",)]
    assert c.execute("SELECT count(*) FROM notes").fetchone() == (0,)


def test_notes_index_wipes_deleted_words():
    """FTS5's own secure-delete option, stored in the table's settings."""
    c = sqlite3.connect(":memory:")
    database.migrate(c)
    assert c.execute("SELECT v FROM notes_config WHERE k = 'secure-delete'").fetchone() == (1,)


def test_connections_overwrite_deleted_data():
    assert database.conn.execute("PRAGMA secure_delete").fetchone() == (1,)


def test_a_forgotten_note_is_gone_from_the_file_itself(tmp_path):
    """Read the raw bytes of the database file: the words must not be anywhere in it."""
    path = tmp_path / "jarvis.db"
    c = database.connect(str(path))
    c.execute("INSERT INTO notes (text, created) VALUES ('Prefers window seats xyzzy', '2030-01-07')")
    c.commit()
    assert b"xyzzy" in path.read_bytes()
    c.execute("DELETE FROM notes WHERE notes MATCH 'xyzzy'")
    c.commit()
    c.close()
    assert b"xyzzy" not in path.read_bytes()
