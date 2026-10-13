"""Back up jarvis.db with SQLite's own backup API.

Safe to run while JARVIS is running: SQLite copies a consistent snapshot even
if the database is being written to. A plain file copy (cp) is NOT safe.

Usage:
    python backup_db.py          take a fresh backup of today now (replaces today's copy)

Called from server.py with overwrite=False, so the first start of each day
keeps a snapshot of how the database looked BEFORE anything touched it.
Backups live in backups/, one file per day, newest 7 days kept.
"""
import sqlite3
import sys
from datetime import date
from pathlib import Path

import config

DB = Path(config.DB_PATH)
BACKUP_DIR = config.BACKUP_DIR
KEEP_DAYS = config.BACKUP_KEEP_DAYS


def backup(overwrite: bool = True) -> Path | None:
    """Returns the backup path, or None if there was nothing to do."""
    if not DB.exists():
        print(f"backup: {DB} does not exist yet, nothing to back up")
        return None

    BACKUP_DIR.mkdir(exist_ok=True)
    dest = BACKUP_DIR / f"jarvis-{date.today().isoformat()}.db"
    if dest.exists() and not overwrite:
        return dest

    # Write to a temporary file first, so a failed backup never replaces a good one
    tmp = dest.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    src = sqlite3.connect(DB)
    out = sqlite3.connect(tmp)
    try:
        src.backup(out)
    finally:
        out.close()
        src.close()

    # Make sure the copy is readable and not corrupt before keeping it
    check = sqlite3.connect(tmp)
    try:
        result = check.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        check.close()
    if result != "ok":
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"backup failed its integrity check: {result}")

    tmp.replace(dest)

    # Keep only the newest KEEP_DAYS backups (the date in the name sorts correctly)
    for old in sorted(BACKUP_DIR.glob("jarvis-*.db"))[:-KEEP_DAYS]:
        old.unlink()

    print(f"backup: saved {dest.name}")
    return dest


if __name__ == "__main__":
    try:
        backup(overwrite=True)
    except Exception as e:
        print(f"backup failed: {e}", file=sys.stderr)
        sys.exit(1)
