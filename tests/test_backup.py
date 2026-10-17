"""Tests for the backups: the plain daily copy, the encrypted copy, restoring, and the keys.

Every test works in pytest's tmp_path folder, never in the real backups/ or jarvis.db.
"""
import sqlite3
from datetime import date, timedelta

import pytest

import backup_crypto
import backup_db
import backup_keys
import restore_backup


@pytest.fixture
def keys():
    """A fresh key pair: (private, public), 32 bytes each."""
    return backup_crypto.generate_keypair()


# --- backup_crypto: locking and unlocking ---------------------------------------------

def test_lock_then_unlock_gives_back_the_same_bytes(keys):
    private, public = keys
    data = b"SQLite format 3\x00" + bytes(range(256)) * 100
    assert backup_crypto.unlock(private, backup_crypto.lock(public, data)) == data


def test_locked_file_starts_with_the_header_and_hides_the_data(keys):
    _, public = keys
    locked = backup_crypto.lock(public, b"Dentist on Friday at 15:00")
    assert locked.startswith(backup_crypto.HEADER)
    assert b"Dentist" not in locked


def test_locking_the_same_data_twice_gives_different_files(keys):
    """A fresh throwaway key and nonce every time (crypto lab, experiments 3 and 4)."""
    _, public = keys
    assert backup_crypto.lock(public, b"same") != backup_crypto.lock(public, b"same")


def test_the_wrong_private_key_is_refused(keys):
    _, public = keys
    other_private, _ = backup_crypto.generate_keypair()
    locked = backup_crypto.lock(public, b"secret")
    with pytest.raises(ValueError, match="wrong key or the file was changed"):
        backup_crypto.unlock(other_private, locked)


@pytest.mark.parametrize("position", [-1, -20, len(backup_crypto.HEADER) + 5,
                                      len(backup_crypto.HEADER) + 40])
def test_one_changed_byte_anywhere_after_the_header_is_refused(keys, position):
    """Tag, ciphertext, nonce and throwaway public key are all covered by the seal."""
    private, public = keys
    locked = bytearray(backup_crypto.lock(public, b"x" * 100))
    locked[position] ^= 1
    with pytest.raises(ValueError, match="wrong key or the file was changed"):
        backup_crypto.unlock(private, bytes(locked))


def test_a_file_that_is_not_a_jarvis_backup_is_refused(keys):
    private, _ = keys
    with pytest.raises(ValueError, match="not an encrypted JARVIS backup"):
        backup_crypto.unlock(private, b"SQLite format 3\x00" + b"\x00" * 100)


def test_an_unknown_version_is_refused_with_a_clear_message(keys):
    private, public = keys
    locked = bytearray(backup_crypto.lock(public, b"x"))
    locked[len(backup_crypto.MAGIC)] = 99
    with pytest.raises(ValueError, match="version 99"):
        backup_crypto.unlock(private, bytes(locked))


def test_a_cut_off_file_is_refused(keys):
    private, public = keys
    locked = backup_crypto.lock(public, b"x" * 100)
    with pytest.raises(ValueError):
        backup_crypto.unlock(private, locked[:40])


# --- backup_crypto: writing keys on paper and reading them back -----------------------

def test_key_written_for_paper_reads_back_the_same(keys):
    private, _ = keys
    text = backup_crypto.format_key(private)
    assert len(text.split()) == 16           # 16 groups of 4 hex characters
    assert backup_crypto.parse_key(text) == private


def test_parse_key_ignores_spaces_dashes_and_capitals(keys):
    private, _ = keys
    messy = "-".join(backup_crypto.format_key(private).upper().split()) + "  "
    assert backup_crypto.parse_key(messy) == private


@pytest.mark.parametrize("bad", ["", "abcd", "zz" * 32, "ab" * 33])
def test_parse_key_rejects_text_that_is_not_a_key(bad):
    with pytest.raises(ValueError):
        backup_crypto.parse_key(bad)


def test_checksum_changes_when_one_character_of_the_key_is_wrong(keys):
    private, _ = keys
    text = backup_crypto.format_key(private)
    typo = ("1" if text[0] != "1" else "2") + text[1:]
    assert backup_crypto.checksum(backup_crypto.parse_key(typo)) != backup_crypto.checksum(private)
    assert len(backup_crypto.checksum(private)) == 8


# --- backup_db: the plain daily backup (existing behaviour, first tests) -------------

@pytest.fixture
def folders(tmp_path, monkeypatch, keys):
    """A small real database file, and every backup path pointed into tmp_path."""
    db = tmp_path / "jarvis.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE events (title TEXT)")
    con.execute("INSERT INTO events VALUES ('Dentist')")
    con.commit()
    con.close()

    _, public = keys
    key_file = tmp_path / "backup_public_key.txt"
    key_file.write_text(public.hex() + "\n")

    monkeypatch.setattr(backup_db, "DB", db)
    monkeypatch.setattr(backup_db, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(backup_db, "ENCRYPTED_DIR", tmp_path / "backups" / "encrypted")
    monkeypatch.setattr(backup_db, "PUBLIC_KEY_PATH", key_file)
    return tmp_path


def _titles(path) -> list[str]:
    con = sqlite3.connect(path)
    try:
        return [row[0] for row in con.execute("SELECT title FROM events")]
    finally:
        con.close()


def test_backup_makes_a_readable_copy_named_after_today(folders):
    dest = backup_db.backup()
    assert dest == folders / "backups" / f"jarvis-{date.today().isoformat()}.db"
    assert _titles(dest) == ["Dentist"]


def test_backup_without_overwrite_keeps_todays_first_copy(folders):
    first = backup_db.backup()
    first.write_bytes(b"the morning snapshot")
    backup_db.backup(overwrite=False)
    assert first.read_bytes() == b"the morning snapshot"


def test_backup_keeps_only_the_newest_seven(folders):
    (folders / "backups").mkdir()
    for day in range(1, 11):
        (folders / "backups" / f"jarvis-2020-01-{day:02d}.db").write_bytes(b"old")
    backup_db.backup()
    kept = sorted(p.name for p in (folders / "backups").glob("jarvis-*.db"))
    assert len(kept) == backup_db.KEEP_DAYS == 7
    assert kept[0] == "jarvis-2020-01-05.db"


# --- backup_db: the encrypted copy ----------------------------------------------------

def test_encrypted_copy_unlocks_to_exactly_the_plain_backup(folders, keys):
    private, _ = keys
    plain = backup_db.backup()
    locked = backup_db.encrypt_copy(plain)
    assert locked == folders / "backups" / "encrypted" / (plain.name + ".enc")
    assert backup_crypto.unlock(private, locked.read_bytes()) == plain.read_bytes()


def test_encrypted_copy_is_skipped_until_a_public_key_exists(folders):
    backup_db.PUBLIC_KEY_PATH.unlink()
    plain = backup_db.backup()
    assert backup_db.encrypt_copy(plain) is None
    assert not (folders / "backups" / "encrypted").exists()


def test_encrypted_copies_keep_the_newest_thirty(folders):
    enc = folders / "backups" / "encrypted"
    enc.mkdir(parents=True)
    for n in range(40):
        day = date(2020, 1, 1) + timedelta(days=n)
        (enc / f"jarvis-{day.isoformat()}.db.enc").write_bytes(b"old")
    backup_db.encrypt_copy(backup_db.backup())
    assert len(list(enc.glob("jarvis-*.db.enc"))) == backup_db.ENCRYPTED_KEEP_DAYS == 30


def test_nightly_run_keeps_the_plain_backup_when_encryption_fails(folders):
    backup_db.PUBLIC_KEY_PATH.write_text("not a key\n")
    assert backup_db.main() == 1
    assert _titles(folders / "backups" / f"jarvis-{date.today().isoformat()}.db") == ["Dentist"]


def test_nightly_run_succeeds_with_both_copies(folders):
    assert backup_db.main() == 0
    assert len(list((folders / "backups" / "encrypted").glob("*.enc"))) == 1


# --- restore_backup -------------------------------------------------------------------

@pytest.fixture
def locked_backup(folders):
    plain = backup_db.backup()
    return plain, backup_db.encrypt_copy(plain)


def test_restore_writes_a_database_identical_to_the_backup(locked_backup, keys, tmp_path):
    private, _ = keys
    plain, locked = locked_backup
    out = restore_backup.restore(locked, private, tmp_path / "jarvis-restored.db")
    assert out.read_bytes() == plain.read_bytes()
    assert _titles(out) == ["Dentist"]


def test_restore_never_overwrites_an_existing_file(locked_backup, keys, tmp_path):
    private, _ = keys
    _, locked = locked_backup
    out = tmp_path / "jarvis-restored.db"
    out.write_bytes(b"keep me")
    with pytest.raises(FileExistsError):
        restore_backup.restore(locked, private, out)
    assert out.read_bytes() == b"keep me"


def test_restore_with_the_wrong_key_leaves_no_file_behind(locked_backup, tmp_path):
    _, locked = locked_backup
    wrong, _ = backup_crypto.generate_keypair()
    out = tmp_path / "jarvis-restored.db"
    with pytest.raises(ValueError, match="wrong key"):
        restore_backup.restore(locked, wrong, out)
    assert not out.exists()


def test_restore_refuses_a_decrypted_file_that_is_not_a_healthy_database(keys, tmp_path):
    private, public = keys
    locked = tmp_path / "odd.db.enc"
    locked.write_bytes(backup_crypto.lock(public, b"this is not a database at all" * 50))
    out = tmp_path / "jarvis-restored.db"
    with pytest.raises(ValueError, match="not a healthy SQLite database"):
        restore_backup.restore(locked, private, out)
    assert not out.exists()


# --- backup_keys ----------------------------------------------------------------------

def test_saved_public_key_is_read_back_by_the_nightly_job(keys, tmp_path):
    _, public = keys
    path = tmp_path / "backup_public_key.txt"
    backup_keys.save_public_key(public, path)
    assert backup_crypto.parse_key(path.read_text()) == public


def test_saving_never_replaces_an_existing_public_key(keys, tmp_path):
    """Replacing it by accident would lock new backups to a key that is not on paper."""
    _, public = keys
    path = tmp_path / "backup_public_key.txt"
    path.write_text("the old key\n")
    with pytest.raises(FileExistsError):
        backup_keys.save_public_key(public, path)
    assert path.read_text() == "the old key\n"


def test_typed_back_copy_matches_however_it_is_spaced(keys):
    private, _ = keys
    typed = backup_crypto.format_key(private).upper().replace(" ", "-")
    assert backup_keys.copy_matches(private, typed)


@pytest.mark.parametrize("mistake", ["typo", "missing", "nonsense"])
def test_typed_back_copy_with_a_mistake_does_not_match(keys, mistake):
    private, _ = keys
    text = backup_crypto.format_key(private)
    typed = {"typo": ("1" if text[0] != "1" else "2") + text[1:],
             "missing": text[:-1],
             "nonsense": "not a key"}[mistake]
    assert not backup_keys.copy_matches(private, typed)


def test_failed_restore_shows_the_typed_keys_check_to_compare_with_the_paper(
        locked_backup, tmp_path, monkeypatch, capsys):
    """The 'check' on paper tells a typo (checks differ) from a wrong key (checks match)."""
    _, locked = locked_backup
    typed_key, _ = backup_crypto.generate_keypair()
    monkeypatch.setattr(restore_backup.getpass, "getpass",
                        lambda prompt: backup_crypto.format_key(typed_key))
    monkeypatch.setattr(restore_backup, "DEFAULT_OUT", tmp_path / "jarvis-restored.db")
    assert restore_backup.main(["restore_backup.py", str(locked)]) == 1
    assert backup_crypto.checksum(typed_key) in capsys.readouterr().err
