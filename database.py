"""The one database connection, its lock, and the schema migrations.

Every module uses `conn` and `lock` from here instead of opening its own
connection. The schema version lives in SQLite's `PRAGMA user_version`;
`migrate()` runs each step newer than that version, once, in order.

To change the schema, add a function to the END of MIGRATIONS. Never edit or
reorder one that has already run on the real database.
"""
import sqlite3
import threading

import config


def _initial_tables(c):
    c.execute(
        "CREATE TABLE IF NOT EXISTS events ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "title TEXT NOT NULL, date TEXT NOT NULL, time TEXT NOT NULL)"
    )
    c.execute(
        "CREATE TABLE IF NOT EXISTS tasks ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "title TEXT NOT NULL, due TEXT, done INTEGER NOT NULL DEFAULT 0)"
    )


def _durations_and_repeats(c):
    # Databases from before versioning may already have some of these columns,
    # because the old code added them on start. Only add what is missing.
    c.execute(
        "CREATE TABLE IF NOT EXISTS event_exceptions ("
        "event_id INTEGER NOT NULL, date TEXT NOT NULL, "
        "PRIMARY KEY (event_id, date))"
    )
    cols = {r[1] for r in c.execute("PRAGMA table_info(events)")}
    for name, ddl in (
        ("end_time", "TEXT"),
        ("repeat_rule", "TEXT NOT NULL DEFAULT 'none'"),
        ("repeat_until", "TEXT"),
        ("repeat_days", "TEXT"),     # e.g. "2,4" for Wed and Fri
    ):
        if name not in cols:
            c.execute(f"ALTER TABLE events ADD COLUMN {name} {ddl}")


def _notes(c):
    # FTS5 is SQLite's full-text search: it keeps an index of every word, so a note can be
    # found by any word in it. created is stored but not indexed.
    c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS notes USING fts5(text, created UNINDEXED)")
    # Make FTS5 wipe a deleted note's words from its index at once, instead of leaving
    # them until the index is next tidied up (SECURITY.md section 5)
    c.execute("INSERT INTO notes (notes, rank) VALUES ('secure-delete', 1)")


MIGRATIONS = [
    _initial_tables,            # 1
    _durations_and_repeats,     # 2
    _notes,                     # 3
]


def version(c) -> int:
    return c.execute("PRAGMA user_version").fetchone()[0]


def migrate(c) -> int:
    """Bring the schema up to date. Returns the version it ended on."""
    current = version(c)
    if current > len(MIGRATIONS):
        raise RuntimeError(
            f"database schema is version {current}, newer than this code "
            f"({len(MIGRATIONS)}). Is this an old copy of JARVIS?"
        )
    for n, step in enumerate(MIGRATIONS[current:], start=current + 1):
        with c:                     # commits at the end, rolls back on an error
            c.execute("BEGIN")      # so the table changes are inside the transaction too
            step(c)
            c.execute(f"PRAGMA user_version = {n}")
    return version(c)


def connect(path: str) -> sqlite3.Connection:
    c = sqlite3.connect(path, check_same_thread=False)
    # Deleted rows are overwritten with zeros, not just marked as free space, so a
    # forgotten note cannot be read back from the file. A connection setting: not saved.
    c.execute("PRAGMA secure_delete = ON")
    migrate(c)
    return c


conn = connect(config.DB_PATH)
lock = threading.RLock()
