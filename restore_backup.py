"""Open an encrypted backup with the private key from paper.

Usage (in your own Terminal, never through an AI tool: anything it runs is sent off
this Mac, and the private key must not be):
    python restore_backup.py backups/encrypted/jarvis-2026-10-17.db.enc

It asks for the private key without showing it or saving it in the shell history, and
writes jarvis-restored.db next to jarvis.db. It never replaces jarvis.db itself: putting
the restored file in place is a deliberate step you take by hand (see the printed steps).
"""
import getpass
import sqlite3
import sys
from pathlib import Path

import backup_crypto
import config

DEFAULT_OUT = config.ROOT / "jarvis-restored.db"


def restore(locked_path: Path, private_key: bytes, out_path: Path) -> Path:
    """Decrypt locked_path into out_path, and only keep it if SQLite says it is healthy."""
    if out_path.exists():
        raise FileExistsError(f"{out_path} already exists; move it away first")

    data = backup_crypto.unlock(private_key, Path(locked_path).read_bytes())

    tmp = out_path.with_suffix(".tmp")
    tmp.write_bytes(data)
    con = sqlite3.connect(tmp)
    try:
        result = con.execute("PRAGMA integrity_check").fetchone()[0]
    except sqlite3.DatabaseError as e:
        result = str(e)
    finally:
        con.close()
    if result != "ok":
        tmp.unlink()
        raise ValueError(f"the decrypted file is not a healthy SQLite database ({result})")

    tmp.replace(out_path)
    return out_path


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 1
    locked = Path(argv[1])
    try:
        private_key = backup_crypto.parse_key(
            getpass.getpass("Private key from paper (hidden as you type): "))
        out = restore(locked, private_key, DEFAULT_OUT)
    except (OSError, ValueError) as e:
        print(f"restore failed: {e}", file=sys.stderr)
        if "wrong key" in str(e):
            print(f"The key you typed has check {backup_crypto.checksum(private_key)}. If the "
                  "paper says something else, it was a typo: try again. If they are the same, "
                  "this file was locked with another key, or it was changed.", file=sys.stderr)
        return 1
    print(f"Restored and checked: {out.name}")
    print("To use it: stop JARVIS, rename jarvis.db to keep it (for example jarvis-old.db),")
    print(f"rename {out.name} to jarvis.db, and start JARVIS again.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
