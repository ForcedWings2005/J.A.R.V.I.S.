"""Crypto lab: small experiments to learn how encryption works, before using it in JARVIS.

Not part of the app. It never touches jarvis.db, config or the network.

Run one experiment at a time, from the project folder with the venv active:
    python experiments/crypto_lab.py 1

    1  Encrypt and decrypt a sentence (AES-GCM)
    2  Change one byte, then decrypt
    3  Encrypt the same sentence twice
    4  Reuse a nonce, and see what leaks
    5  Two keys: lock with the public key (X25519)
    6  Turn a passphrase into a key (scrypt)

Words used below:
    plaintext   the readable message
    ciphertext  the scrambled result
    key         the secret that locks and unlocks. 32 random bytes = 256 bits.
    nonce       "number used once": 12 random bytes, new for every message.
                Not secret, it is stored next to the ciphertext.
    tag         16 bytes added to the ciphertext that prove nothing was changed.

About "hazmat": the library keeps its low-level tools under cryptography.hazmat
("hazardous materials"). They are safe when used correctly, but they let you make
mistakes, such as reusing a nonce. That is what this lab is for.
"""
import os
import sys
import time

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt


def show(label: str, data: bytes) -> None:
    """Print bytes as hex: two characters per byte, so you can compare them by eye."""
    print(f"{label:<12} {len(data):>3} bytes  {data.hex()}")


def xor(a: bytes, b: bytes) -> bytes:
    """Combine two byte strings bit by bit. XOR twice with the same value undoes itself."""
    return bytes(x ^ y for x, y in zip(a, b, strict=False))


# --- 1. Encrypt and decrypt -------------------------------------------------------------

def experiment_1() -> None:
    """The basic round trip: plaintext + key + nonce -> ciphertext, and back."""
    key = AESGCM.generate_key(bit_length=256)    # 32 random bytes from the operating system
    nonce = os.urandom(12)                       # fresh for this message, never reused
    plaintext = b"Dentist on Friday at 15:00"

    ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)

    show("key", key)
    show("nonce", nonce)
    show("plaintext", plaintext)
    show("ciphertext", ciphertext)
    print(f"\nThe ciphertext is {len(ciphertext) - len(plaintext)} bytes longer: that is the tag.")

    back = AESGCM(key).decrypt(nonce, ciphertext, None)
    print(f"Decrypted:   {back.decode()}")

    wrong_key = AESGCM.generate_key(bit_length=256)
    try:
        AESGCM(wrong_key).decrypt(nonce, ciphertext, None)
    except InvalidTag:
        print("Wrong key:   refused (InvalidTag). It does not return rubbish, it refuses.")

    # Try this: run the experiment twice. Every line except the plaintext changes,
    # because the key and the nonce are random each time.


# --- 2. Change one byte -------------------------------------------------------------

def experiment_2() -> None:
    """Show that AES-GCM notices when the ciphertext has been changed.

    Steps:
      1. Encrypt a sentence as in experiment 1.
      2. Make a changeable copy:  changed = bytearray(ciphertext)
      3. Flip one bit of one byte:  changed[0] ^= 1
      4. Decrypt bytes(changed) inside try / except InvalidTag, and print what happens.

    Then try changing the nonce instead of the ciphertext. What happens, and why?
    The question to answer: why is refusing better than returning slightly wrong text?
    """
    key = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(nonce, b"Dentist on Friday at 15:00", None)

    # bytes cannot be changed once made; a bytearray is the changeable version
    changed = bytearray(ciphertext)
    # ^= 1 flips the lowest bit: the first byte goes from, say, 0xd8 to 0xd9
    changed[0] ^= 1
    changed = bytes(changed)

    show("original", ciphertext)
    show("changed", changed)
    differing = sum(a != b for a, b in zip(ciphertext, changed, strict=True))
    print(f"Bytes that differ: {differing} of {len(ciphertext)}\n")

    # The original still decrypts, so the key and nonce are fine
    print(f"Original:    {AESGCM(key).decrypt(nonce, ciphertext, None).decode()}")

    try:
        AESGCM(key).decrypt(nonce, changed, None)
        print("Changed:     decrypted (this should never happen)")
    except InvalidTag:
        print("Changed:     refused (InvalidTag). One flipped bit, and the seal no longer matches.")

    # Bonus: leave the ciphertext alone and change the nonce instead
    other_nonce = bytearray(nonce)
    other_nonce[0] ^= 1
    try:
        AESGCM(key).decrypt(bytes(other_nonce), ciphertext, None)
        print("Nonce:       decrypted (this should never happen)")
    except InvalidTag:
        print("Nonce:       refused too. The tag covers the nonce, so it can't be swapped.")


# --- 3. Same sentence twice ---------------------------------------------------------

def experiment_3() -> None:
    """Encrypt the same sentence twice with the same key, each time with a fresh nonce.

    Steps:
      1. One key. Two nonces, each from os.urandom(12).
      2. Encrypt the same plaintext with each nonce, and show() both ciphertexts.
      3. Print whether they are equal.

    The question to answer: if the same sentence always gave the same ciphertext, what
    could someone learn from a pile of encrypted backups without ever decrypting one?
    """
    key = AESGCM.generate_key(bit_length=256)
    plaintext = b"Dentist on Friday at 15:00"

    # Same key, same sentence, but each message gets its own fresh nonce
    nonce_a, nonce_b = os.urandom(12), os.urandom(12)
    first = AESGCM(key).encrypt(nonce_a, plaintext, None)
    second = AESGCM(key).encrypt(nonce_b, plaintext, None)

    show("first", first)
    show("second", second)
    print(f"Same ciphertext? {first == second}")

    # Both still decrypt to the same sentence, each with its own nonce
    same = AESGCM(key).decrypt(nonce_a, first, None) == AESGCM(key).decrypt(nonce_b, second, None)
    print(f"Same sentence after decrypting? {same}")
    print("\nWithout the key, nobody can tell these are the same message. If they were")
    print("identical, an attacker could spot repeats: 'this backup is the same as yesterday's'.")


# --- 4. Reuse a nonce ---------------------------------------------------------------

def experiment_4() -> None:
    """Break the one rule on purpose: the same key AND the same nonce for two messages.

    AES-GCM turns key + nonce into a stream of random-looking bytes, then XORs the
    plaintext with it. Reuse the nonce and both messages are XORed with the SAME stream.
    XOR the two ciphertexts together and the stream cancels out, leaving
    plaintext1 XOR plaintext2.

    Steps:
      1. One key, ONE nonce.
      2. Encrypt two messages of the same length (30 bytes each here), for example
         b"Lock code for the garage: 4417" and b"Bank PIN reminder: card ends 4"
      3. Drop the 16-byte tag from each: ciphertext[:-16]
      4. leak = xor(ciphertext1, ciphertext2), and compare it with xor(plain1, plain2).
      5. Now pretend you are the attacker and you guessed message 1. Print
         xor(leak, plain1). What comes out?

    The question to answer: you never had the key. How did you read message 2?
    """
    key = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)                       # the mistake: one nonce for two messages
    plain1 = b"Lock code for the garage: 4417"
    plain2 = b"Bank PIN reminder: card ends 4"

    # [:-16] drops the tag, leaving only the encrypted bytes, one per letter
    cipher1 = AESGCM(key).encrypt(nonce, plain1, None)[:-16]
    cipher2 = AESGCM(key).encrypt(nonce, plain2, None)[:-16]
    show("cipher 1", cipher1)
    show("cipher 2", cipher2)

    # Each ciphertext is plaintext XOR stream. With the same stream twice, XORing the two
    # ciphertexts cancels the stream: (p1 ^ s) ^ (p2 ^ s) = p1 ^ p2. The key is gone.
    leak = xor(cipher1, cipher2)
    show("c1 XOR c2", leak)
    show("p1 XOR p2", xor(plain1, plain2))
    print(f"Equal? {leak == xor(plain1, plain2)}: the attacker now holds p1 XOR p2, no key needed.\n")

    # The attacker guesses message 1 (garage codes and greetings are easy to guess)
    recovered = xor(leak, plain1)
    print(f"Guess message 1, and out comes message 2: {recovered.decode()}")

    # Even a partial guess works: knowing only how message 1 starts reveals how 2 starts
    partial = xor(leak[:9], b"Lock code")
    print(f"Guess only 'Lock code', and out comes:     {partial.decode()}")


# --- 5. Two keys ----------------------------------------------------------------------

def _derive_key(shared_secret: bytes) -> bytes:
    """Turn the X25519 shared secret into an AES key. HKDF mixes it into a clean 32-byte key."""
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                info=b"jarvis crypto lab").derive(shared_secret)


def lock(public_key: X25519PublicKey, plaintext: bytes) -> bytes:
    """Encrypt for whoever holds the private key. Needs only the public key."""
    # A throwaway key pair, used for this one message and then forgotten
    ephemeral = X25519PrivateKey.generate()
    aes_key = _derive_key(ephemeral.exchange(public_key))
    nonce = os.urandom(12)
    ciphertext = AESGCM(aes_key).encrypt(nonce, plaintext, None)
    # Everything the owner needs to unlock it, except the private key itself
    ephemeral_public = ephemeral.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return ephemeral_public + nonce + ciphertext


def unlock(private_key: X25519PrivateKey, box: bytes) -> bytes:
    """Decrypt with the private key. Raises InvalidTag if the box was changed."""
    ephemeral_public = X25519PublicKey.from_public_bytes(box[:32])
    nonce, ciphertext = box[32:44], box[44:]
    aes_key = _derive_key(private_key.exchange(ephemeral_public))
    return AESGCM(aes_key).decrypt(nonce, ciphertext, None)


def experiment_5() -> None:
    """The mailbox: anyone with the public key can lock, only the private key can unlock.

    How X25519 works, in short: it does not lock things directly. Two key pairs can each
    combine their own private key with the other's public key, and both get the SAME
    shared secret ("key agreement"). So lock() makes a throwaway key pair, agrees a secret
    with your public key, and uses that secret as an AES key. unlock() redoes the
    agreement from the other side, with your private key, and gets the same AES key.
    """
    private_key = X25519PrivateKey.generate()    # on paper, never on the Mac
    public_key = private_key.public_key()        # on the Mac, used by the 03:00 job

    raw = serialization.Encoding.Raw
    show("private key", private_key.private_bytes(raw, serialization.PrivateFormat.Raw,
                                                  serialization.NoEncryption()))
    show("public key", public_key.public_bytes(raw, serialization.PublicFormat.Raw))
    print("The private key is 64 hex characters: short enough to write on paper.\n")

    box = lock(public_key, b"A whole backup file would go here")
    show("locked box", box)
    print("  = 32 bytes throwaway public key + 12 bytes nonce + ciphertext + 16 bytes tag")

    print(f"\nUnlocked:    {unlock(private_key, box).decode()}")

    someone_else = X25519PrivateKey.generate()
    try:
        unlock(someone_else, box)
    except InvalidTag:
        print("Other key:   refused (InvalidTag).")

    print("\nThe public key has no way to unlock: "
          f"hasattr(public_key, 'exchange') = {hasattr(public_key, 'exchange')}")
    # Try this: lock() the same message twice. Are the boxes the same? Why not?


# --- 6. Passphrase to key -----------------------------------------------------------

def experiment_6() -> None:
    """A passphrase is not a key: it is too short and too guessable. scrypt stretches it
    into a 32-byte key, and is deliberately slow, so guessing millions of passphrases
    is slow too.

    Steps:
      1. salt = os.urandom(16)   (stored with the result, so the same passphrase gives
         different keys for different files)
      2. kdf = Scrypt(salt=salt, length=32, n=2**14, r=8, p=1)
      3. Time it:  start = time.perf_counter(); key = kdf.derive(b"correct horse battery")
      4. Print the key and the time. Then try n=2**17 and n=2**20. What happens to the time?
         (A Scrypt object can only derive once, so make a new one each time.)

    The question to answer: an attacker trying 1 billion passphrases pays that time
    1 billion times. How long would that take at each setting?
    """
    passphrase = b"correct horse battery"
    # The salt is random and stored with the result. It means the attacker can't compute
    # one big table of "passphrase -> key" in advance and reuse it for every file.
    salt = os.urandom(16)
    show("salt", salt)
    print()

    guesses = 1_000_000_000
    # n is the cost: each step up of x8 makes scrypt use 8x the time and 8x the memory
    for exponent in (14, 17, 20):
        # A Scrypt object can derive only once, so make a new one each time
        kdf = Scrypt(salt=salt, length=32, n=2**exponent, r=8, p=1)
        start = time.perf_counter()
        key = kdf.derive(passphrase)
        seconds = time.perf_counter() - start
        years = seconds * guesses / (60 * 60 * 24 * 365)
        print(f"n = 2**{exponent}: {seconds:6.3f} s per guess, "
              f"{128 * 8 * 2**exponent // 2**20:>4} MB memory, "
              f"1 billion guesses = {years:,.1f} years on one core")
        print(f"            key {key.hex()}")

    # Same passphrase, same salt, same settings: always the same key. That is what lets
    # you unlock things again later with only the passphrase.
    first = Scrypt(salt=salt, length=32, n=2**14, r=8, p=1).derive(passphrase)
    again = Scrypt(salt=salt, length=32, n=2**14, r=8, p=1).derive(passphrase)
    print(f"\nSame passphrase and salt give the same key again? {again == first}")

    other_salt = Scrypt(salt=os.urandom(16), length=32, n=2**14, r=8, p=1).derive(passphrase)
    print(f"Same passphrase, different salt, same key?        {other_salt == first}")
    print("\nThe years assume one computer. Attackers use thousands in parallel, which is why a")
    print("long passphrase matters as much as a slow setting.")


EXPERIMENTS = {"1": experiment_1, "2": experiment_2, "3": experiment_3,
               "4": experiment_4, "5": experiment_5, "6": experiment_6}

if __name__ == "__main__":
    choice = sys.argv[1] if len(sys.argv) > 1 else ""
    if choice not in EXPERIMENTS:
        print(__doc__)
        sys.exit(1)
    EXPERIMENTS[choice]()
