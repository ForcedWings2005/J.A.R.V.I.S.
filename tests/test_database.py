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
