"""Back up jarvis.db with SQLite's own backup API.

Safe to run while JARVIS is running: SQLite copies a consistent snapshot even
if the database is being written to. A plain file copy (cp) is NOT safe.

Usage:
    python backup_db.py          take a fresh backup of today now (replaces today's copy),
                                 then an encrypted copy of it (the 03:00 job runs this)

Called from server.py with overwrite=False, so the first start of each day
keeps a snapshot of how the database looked BEFORE anything touched it.
Backups live in backups/, one file per day, newest 7 days kept.

Encrypted copies live in backups/encrypted/, newest 30 kept. They are the ones that may
leave this Mac (copy them to iCloud Drive). Only the private key on paper can open them;
restore one with restore_backup.py.
"""
import sqlite3
import sys
from datetime import date
from pathlib import Path

import config

DB = Path(config.DB_PATH)
BACKUP_DIR = config.BACKUP_DIR
KEEP_DAYS = config.BACKUP_KEEP_DAYS
ENCRYPTED_DIR = config.BACKUP_ENCRYPTED_DIR
ENCRYPTED_KEEP_DAYS = config.BACKUP_ENCRYPTED_KEEP_DAYS
PUBLIC_KEY_PATH = config.BACKUP_PUBLIC_KEY


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


def encrypt_copy(plain: Path) -> Path | None:
    """Lock a finished backup with the public key. Returns None until a key pair exists."""
    if not PUBLIC_KEY_PATH.exists():
        print("backup: no public key yet (run backup_keys.py), encrypted copy skipped")
        return None

    # Imported here, not at the top: server.py imports this module at start-up, and a
    # problem with the cryptography library must never stop the plain backup or JARVIS.
    import backup_crypto

    public_key = backup_crypto.parse_key(PUBLIC_KEY_PATH.read_text())
    ENCRYPTED_DIR.mkdir(parents=True, exist_ok=True)
    dest = ENCRYPTED_DIR / (plain.name + ".enc")
    tmp = dest.with_suffix(".tmp")
    tmp.write_bytes(backup_crypto.lock(public_key, plain.read_bytes()))
    tmp.replace(dest)

    for old in sorted(ENCRYPTED_DIR.glob("jarvis-*.db.enc"))[:-ENCRYPTED_KEEP_DAYS]:
        old.unlink()

    print(f"backup: encrypted {dest.name}")
    return dest


def main() -> int:
    """The nightly job. The plain backup comes first, so a failed encryption never costs it."""
    try:
        plain = backup(overwrite=True)
    except Exception as e:
        print(f"backup failed: {e}", file=sys.stderr)
        return 1
    if plain is None:
        return 0
    try:
        encrypt_copy(plain)
    except Exception as e:
        print(f"backup: encrypted copy failed (plain backup kept): {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
