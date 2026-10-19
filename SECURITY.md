# JARVIS security: threat model

Written 2026-10-14. Review it when anything in "When to revisit" happens.

This file answers four questions: what JARVIS holds, who could harm it, how they could get
in, and what stops them. Decisions about security should start here, not with a tool. The
point is to protect the right thing: encrypting the database does nothing if the same text
sits readable in the log.

## 1. What we protect (assets)

Each asset is rated on the three security properties:

- **Confidentiality**: only I can read it.
- **Integrity**: nobody can change it without me knowing.
- **Availability**: it is there when I need it.

| Asset | Where it lives | Most important | Why |
|---|---|---|---|
| Calendar events | `jarvis.db` | Availability, then confidentiality | Losing it is the most likely harm. It also shows where I will be and when. |
| Tasks | `jarvis.db` | Availability | Annoying to lose, not secret. |
| Notes and memory (Phase 5, planned) | `jarvis.db` | Integrity | Only trivial preferences (favourite food, places). A false "preference" would change how JARVIS behaves in every later conversation. |
| Daily backups | `backups/`, 7 kept | Same as the database | Each one is a full copy of everything above. |
| The log | `logs/jarvis.log` plus up to 5 older files of 1 MB each; also printed in the terminal | Confidentiality | Holds the first 300 characters of every message I send, and every tool call with its inputs and results. |
| The current conversation | Server memory only | Low | Lost on restart, by design (plan.md, Phase 4). |
| Voice recordings | A temporary file during transcription | Confidentiality | Deleted straight after, every time. |

**Data copies itself.** One sentence typed to JARVIS can end up in the database, 7 backups,
the log and the terminal. The weakest copy decides how safe it really is.

## 2. Who could cause harm (threat actors)

A threat actor is anyone or anything that could cause harm, including accidents.

| Actor | How likely | Notes |
|---|---|---|
| **Hardware failure, loss or theft of the Mac** | Most likely | Takes the database and every backup at once, because they are on the same disk. |
| **My own mistakes** (deleting the wrong thing, a bad migration) | Likely | Has happened once already (CHANGELOG section 23). |
| **Software I install** (pip packages, Steam games, apps) | Possible | Runs with my permissions and can read every file JARVIS can. A compromised package update is called a *supply chain attack*. |
| **A website in another browser tab** | Possible | Can send requests to `127.0.0.1:8000` while the server runs. |
| **Text that tricks the model** (*prompt injection*) | Possible later | Today the model only sees what I type. Once news or web tools exist, outside text reaches it. |
| **AI coding tools in this folder** (Claude Code) | Trusted, with limits | Can read `jarvis.db` and the log like any program I run. Controlled by CLAUDE.md and by my approval of what it runs, not by encryption. |
| **Another person with the laptop** | Unlikely | I am the only user, and it locks when it sleeps. |
| **Someone on the network** | Very unlikely today | The server listens only on this Mac. Becomes real in Phase 6. |

## 3. Ways in (attack surface)

- **The HTTP endpoints**: `/chat`, `/confirm`, `/calendar`, `/tasks`, `/transcribe`, `/speak`.
  Reachable only from this Mac, but including from other browser tabs.
- **Files on disk**: `jarvis.db`, `backups/`, `logs/`. Readable by anything running as me.
- **The model**: anything it reads can try to steer it.
- **Dependencies**: 72 packages in `requirements.txt`, about 10 chosen directly.
- **Off-disk backups** (planned, see section 5): a new copy of the data outside this Mac.

## 4. Controls in place today

Each of these is in the code or the system and has been checked.

| Control | Protects against |
|---|---|
| FileVault (whole-disk encryption) is on | A stolen or lost Mac while it is off or locked. Does **not** protect anything while I am logged in. |
| Screen locks on sleep, password to wake | Someone using the Mac while I am away. Gap: the minutes before it sleeps. Habit: lock it when stepping away. |
| Server listens on `127.0.0.1` only | Everything on the network. |
| `TrustedHostMiddleware` allows only `127.0.0.1` and `localhost` | DNS rebinding (a website pretending to be this Mac). |
| JSON endpoints refuse `text/plain` bodies (pinned by a test) | Other websites driving `/chat`, `/confirm` or `/tasks`. |
| Deletes and edits only through a confirmation card and `POST /confirm` | The model deleting or changing events by itself. |
| Input limits (upload size, text length, date ranges, calculator) | Requests that use up memory or time. |
| Every SQL value goes through `?` parameters | SQL injection. |
| Calculator parses with `ast`, never `eval` | Running arbitrary code through arithmetic. |
| Pinned dependency versions | A bad new release being installed without my knowing. |
| Daily backups, integrity-checked, 7 kept | Software mistakes and corruption. Not hardware loss (same disk). |
| `jarvis.db`, `backups/`, `logs/`, `evals/results/`, `.env` are in `.gitignore` | Personal data being pushed to GitHub. |

## 5. Decisions

### Backups: encrypted, and a copy off this Mac (Phase 5, item 3)

The biggest real risk is losing the Mac, which takes every backup with it. Built
(CHANGELOG section 32):

- The project's rule changed with my agreement: nothing leaves the Mac **unencrypted**,
  and only I hold the key. The encrypted backups are the only thing that leaves.
- Each night, after the plain backup, `backup_db.py` writes an encrypted copy to
  `backups/encrypted/` (30 kept). I copy that folder to iCloud Drive by hand (route B).
  iCloud gives the offsite copy; the encryption means only I can read it. (Advanced Data
  Protection is off, so without our own encryption Apple would hold the key.)
- Why by hand: macOS privacy protection (TCC) blocks programs from iCloud Drive unless
  allowed. The 03:00 job has no window to ask, and giving Python Full Disk Access would let
  every Python script read everything. Still to test (route A): a copy made when I start the
  server from Terminal, which may already have the permission.
- **Two keys** (X25519 public-key encryption, `backup_crypto.py`). The **public key** is in
  `backup_public_key.txt`, in git: it can only lock, so the 03:00 job runs unattended and a
  stolen public key opens nothing. The **private key** can only unlock, and never lives on
  the Mac.
- Each file gets its own throwaway key pair and nonce. The header and throwaway public key
  are covered by the tag, so nothing in the file can be changed without it being refused.
- The private key is kept **on paper**, with a short check value to catch copying mistakes.
  `backup_keys.py` makes me type it back before saving the public key. If the paper is lost,
  every encrypted backup is lost with it (encryption trades some availability for
  confidentiality); the plain local backups are unaffected.
- `restore_backup.py` writes `jarvis-restored.db`, checks it, and never replaces
  `jarvis.db`. AI tools must never run either script or see the private key (CLAUDE.md).
- A failed encryption never costs the plain backup: it runs second, separately, and the
  server's start-up does not encrypt at all.
- Tested (`tests/test_backup.py`): round trip, wrong key, changed bytes, wrong version, cut-off
  files, restore checks. Restore drill with the real paper key: passed on 2026-10-18
  (CHANGELOG section 33). The first copies are in iCloud Drive.

Later: Time Machine on an external drive, for the rest of the Mac as well.

### Notes and memory (Phase 5, item 4)

Notes are for **trivial preferences only**: favourite food, places, how I like replies.
Built in `notes.py` (CHANGELOG section 34).

- **No passwords, codes or secrets.** `remember` refuses text that looks like one (words
  such as password or PIN, 6 or more digits in a row, password-shaped words) and points to a
  password manager. A safety net, not a guarantee. A password in JARVIS would be in the
  database, the model's context, the screen, the speakers and the backups. Encrypting one
  of those copies would not protect the others.
- **Only I can make JARVIS remember something.** `remember` only shows a card; the note is
  saved when I click it. So a model talked into saving something, by me or by text from a
  tool, can only ask. This protects integrity.
- **Recalled notes are data, not instructions.** The tool result says so. Deletes and edits
  still need the confirmation card, so a planted note cannot act on its own.
- **`forget` uses the confirmation card**, like `delete_event`, and checks again when I
  click. A forgotten note can stay in the plain backups for 7 days, in the encrypted
  copies for 30, and in iCloud Drive until I delete the old copies there.
- **The log never records what the note tools were given or returned**, or a note card's
  text: only lengths, such as `tool remember(23 characters)`. My own message ("remember
  that ...") and JARVIS's reply are still logged like any other turn. I chose that: notes
  are trivial, and the log is needed for debugging (see gap 2).
- **Deleted notes are wiped from the file**: `PRAGMA secure_delete` on every connection,
  and FTS5's own secure-delete option. A test reads the raw file to prove it.
- **Search words are plain words.** FTS5 has its own search language (OR, NOT, quotes, *);
  `recall` and `forget` turn any text into quoted plain terms first.
- **Limits**: 300 characters per note, 5 notes per `recall`.
- Notes stay searchable with SQLite FTS5. They are not encrypted on their own: at this
  sensitivity, FileVault is enough on this Mac, and the backups are encrypted (above).

## 6. Known gaps

In rough order of importance.

1. **Offsite backups depend on a habit.** Encrypted copies are in iCloud Drive (section 5),
   but only as recent as the last time I copied them by hand. Route A (a copy made when
   the server starts) would remove the habit; not tried yet.
2. **The log holds message text** (first 300 characters of each message, and tool inputs
   and results), in up to 6 MB of files and the terminal. The note tools and note cards
   are logged as lengths only (section 5), but a message such as "remember that ..." is
   logged like any other: a known trade-off for being able to debug.
3. **`/transcribe` has no `Origin` check.** Another website can upload audio to it. It
   cannot read the reply, but the check should exist (plan.md, Phase 6 item 1).
4. **Files are readable by group and others** (`-rw-r--r--`). Low risk while I am the only
   user, but `chmod 600` on the files and `700` on the folders is free.
5. **Dependencies are pinned by version, not by hash.** A version on PyPI could in theory
   be replaced; hash checking (`pip install --require-hashes`) would catch that.
6. **No login and no HTTPS.** Acceptable only while the server stays on `127.0.0.1`.

## 7. Accepted risks

- **Software running as me can read `jarvis.db`.** JARVIS has to read it, so anything
  running as me can too. Encrypting the database would not change this, because the key
  would also be on the Mac. The controls are FileVault, installing little, and pinned
  versions.
- **AI coding tools can read personal data in this folder.** Accepted because I approve
  what they run and CLAUDE.md sets the rules.

## 8. When to revisit

- Before Phase 6 (anything leaving `127.0.0.1`): the network becomes an attack surface, and
  a login, HTTPS and the `Origin` check are needed first.
- Before adding a tool that reads outside content (news, weather, web): prompt injection
  becomes real.
- If JARVIS is ever asked to hold something more sensitive than it does today.
- If someone else starts using this Mac.
