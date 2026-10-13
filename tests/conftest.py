"""Shared test setup.

Two safety rules live here:
1. Tests use a throwaway in-memory database, never your real jarvis.db.
2. Tests use a frozen clock (Monday 2030-01-07, 08:00), so they pass on any day.
"""
import os

# This must happen BEFORE anything imports config, because the database opens on import.
os.environ["JARVIS_DB"] = ":memory:"

from datetime import datetime  # noqa: E402

import pytest  # noqa: E402

import database  # noqa: E402
import jcal  # noqa: E402


class Clock:
    """The fake 'now'. Tests move it with clock.set(hour, minute, day)."""

    def __init__(self):
        self.now = datetime(2030, 1, 7, 8, 0)      # a Monday

    def set(self, hour, minute=0, day=7):
        self.now = datetime(2030, 1, day, hour, minute)


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    """Runs before every test: empty database, frozen clock."""
    with database.lock:
        database.conn.execute("DELETE FROM events")
        database.conn.execute("DELETE FROM event_exceptions")
        database.conn.execute("DELETE FROM tasks")
        database.conn.commit()

    fake = Clock()

    class FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            n = fake.now
            return cls(n.year, n.month, n.day, n.hour, n.minute)

    monkeypatch.setattr(jcal, "datetime", FakeDateTime)
    return fake
