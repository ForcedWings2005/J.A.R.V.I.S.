"""Make the key pair for encrypted backups. Run it once, yourself, in your own Terminal.

    python backup_keys.py

Never run it through an AI tool: whatever such a tool runs is sent off this Mac, and the
private key would go with it.

What happens:
  1. A new key pair is made.
  2. The private key is shown once. Write it on paper, with the details printed under it.
  3. The screen is cleared, and you type the key back from the paper. This proves the
     paper copy is right while it can still be fixed.
  4. Only then is the PUBLIC key saved, to backup_public_key.txt. The private key is
     never written to disk; when this script ends, the paper is the only copy.
"""
import getpass
import sys
from datetime import date
from pathlib import Path

import backup_crypto
import config

TRIES = 3
# Erase the screen and the scrollback (Terminal and iTerm), so the key cannot be
# scrolled back to after it is written down
CLEAR_SCREEN = "\033[2J\033[3J\033[H"


def save_public_key(public_key: bytes, path: Path) -> None:
    """Never replaces an existing key: new backups would then need a key that is not on paper."""
    if path.exists():
        raise FileExistsError(
            f"{path.name} already exists. To start over with a new key pair, rename it first; "
            "keep the old paper key for backups made before.")
    path.write_text(public_key.hex() + "\n")


def copy_matches(private_key: bytes, typed: str) -> bool:
    try:
        return backup_crypto.parse_key(typed) == private_key
    except ValueError:
        return False


def main() -> int:
    path = config.BACKUP_PUBLIC_KEY
    if path.exists():
        print(f"{path.name} already exists, so a key pair is already set up. Nothing changed.")
        return 1

    private_key, public_key = backup_crypto.generate_keypair()
    print("Your PRIVATE key. Write all of it on paper, exactly as shown:\n")
    print(f"    {backup_crypto.format_key(private_key)}")
    print(f"\n    check: {backup_crypto.checksum(private_key)}\n")
    print("Write these next to it, so the paper still makes sense in a year:")
    print(f"    JARVIS backup private key, made {date.today().isoformat()}")
    print("    Opens the files in backups/encrypted/ and their copies in iCloud Drive")
    print("    Restore: python restore_backup.py <file>.db.enc\n")
    print("Keep it somewhere safe and private. Without it the encrypted backups cannot be")
    print("opened by anyone, including you.\n")
    input("Press Return when it is written down. The screen will then be cleared.")
    print(CLEAR_SCREEN, end="", flush=True)

    for attempt in range(1, TRIES + 1):
        typed = getpass.getpass(f"Type the key back from the paper (hidden), try {attempt} of {TRIES}: ")
        if copy_matches(private_key, typed):
            save_public_key(public_key, path)
            print(f"\nThe paper copy is right. Public key saved to {path.name}.")
            print("Tonight's 03:00 backup will make the first encrypted copy.")
            return 0
        print("That does not match. Check each group of 4 on the paper is clear, "
              "then type it again.")

    print("\nNo match after 3 tries. Nothing was saved, and this key pair is gone, so the paper")
    print("copy is useless now: destroy it and run this script again.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
