"""Encryption for backups that leave this Mac (SECURITY.md section 5).

Two keys. The public key is on the Mac and can only lock. The private key is on paper,
never on the Mac, and is the only thing that can unlock. So the 03:00 job can encrypt
without anyone awake, and a stolen Mac or a leaked iCloud folder opens nothing.

How one file is locked (the design tried in experiments/crypto_lab.py, experiment 5):
a throwaway X25519 key pair is made for this file only. Its private half and our public
key agree on a shared secret, HKDF turns that into an AES key, and AES-GCM encrypts the
data. The throwaway private half is then forgotten; only the owner's private key can
recreate the same secret.

File layout:
    HEADER (9)  "JARVISBK" + version byte
    32          the throwaway public key
    12          the nonce
    rest        ciphertext + 16-byte tag
The header and the throwaway public key are not secret but are covered by the tag
("associated data"), so they cannot be changed or swapped without the file being refused.
"""
import hashlib
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

MAGIC = b"JARVISBK"
VERSION = 1
HEADER = MAGIC + bytes([VERSION])
KEY_BYTES = 32
NONCE_BYTES = 12
TAG_BYTES = 16

_RAW = serialization.Encoding.Raw


def _raw(public: X25519PublicKey) -> bytes:
    return public.public_bytes(_RAW, serialization.PublicFormat.Raw)


def generate_keypair() -> tuple[bytes, bytes]:
    """Returns (private, public), 32 bytes each. The private key belongs on paper only."""
    private = X25519PrivateKey.generate()
    private_bytes = private.private_bytes(_RAW, serialization.PrivateFormat.Raw,
                                          serialization.NoEncryption())
    return private_bytes, _raw(private.public_key())


def _aes_key(shared_secret: bytes, throwaway_public: bytes, owner_public: bytes) -> bytes:
    """Both public keys go into the salt, so the AES key belongs to this one file and owner."""
    return HKDF(algorithm=hashes.SHA256(), length=KEY_BYTES,
                salt=throwaway_public + owner_public,
                info=b"jarvis backup v1").derive(shared_secret)


def lock(public_key: bytes, data: bytes) -> bytes:
    """Encrypt data so that only the matching private key can read it."""
    owner = X25519PublicKey.from_public_bytes(public_key)
    throwaway = X25519PrivateKey.generate()
    throwaway_public = _raw(throwaway.public_key())
    aes_key = _aes_key(throwaway.exchange(owner), throwaway_public, public_key)
    nonce = os.urandom(NONCE_BYTES)
    ciphertext = AESGCM(aes_key).encrypt(nonce, data, HEADER + throwaway_public)
    return HEADER + throwaway_public + nonce + ciphertext


def unlock(private_key: bytes, locked: bytes) -> bytes:
    """Decrypt a locked file. Raises ValueError with a plain message if it cannot."""
    if not locked.startswith(MAGIC):
        raise ValueError("not an encrypted JARVIS backup")
    version = locked[len(MAGIC)] if len(locked) > len(MAGIC) else None
    if version != VERSION:
        raise ValueError(f"this backup is version {version}, this code reads version {VERSION}")
    start = len(HEADER)
    if len(locked) < start + KEY_BYTES + NONCE_BYTES + TAG_BYTES:
        raise ValueError("the file is too short: it was cut off or damaged")

    throwaway_public = locked[start:start + KEY_BYTES]
    nonce = locked[start + KEY_BYTES:start + KEY_BYTES + NONCE_BYTES]
    ciphertext = locked[start + KEY_BYTES + NONCE_BYTES:]

    owner = X25519PrivateKey.from_private_bytes(private_key)
    try:
        shared = owner.exchange(X25519PublicKey.from_public_bytes(throwaway_public))
        aes_key = _aes_key(shared, throwaway_public, _raw(owner.public_key()))
        return AESGCM(aes_key).decrypt(nonce, ciphertext, HEADER + throwaway_public)
    except (InvalidTag, ValueError):
        # A changed throwaway key can even make the exchange itself fail; same answer.
        raise ValueError("wrong key or the file was changed") from None


def format_key(key: bytes) -> str:
    """The key as 16 groups of 4 hex characters, easier to copy onto paper without mistakes."""
    text = key.hex()
    return " ".join(text[i:i + 4] for i in range(0, len(text), 4))


def parse_key(text: str) -> bytes:
    """Read a key typed back from paper. Spaces, dashes and capitals don't matter."""
    cleaned = "".join(ch for ch in text.lower() if ch not in " -\t\n")
    if len(cleaned) != KEY_BYTES * 2:
        raise ValueError(f"a key is {KEY_BYTES * 2} hex characters, this has {len(cleaned)}")
    try:
        return bytes.fromhex(cleaned)
    except ValueError:
        raise ValueError("a key uses only 0-9 and a-f") from None


def checksum(key: bytes) -> str:
    """A short fingerprint (8 characters) written next to the key, to catch copying mistakes."""
    return hashlib.sha256(b"jarvis key check" + key).hexdigest()[:8]
