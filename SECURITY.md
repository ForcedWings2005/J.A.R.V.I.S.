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

- **The HTTP endpoints**: `/chat`, `/confirm`, `/calendar`, `/tasks`, `/transcribe`, `/speak`,
  `/weather/places`, `/weather/confirm`, `/weather/home`.
  Reachable only from this Mac, but including from other browser tabs.
- **Files on disk**: `jarvis.db`, `backups/`, `logs/`. Readable by anything running as me.
- **The model**: anything it reads can try to steer it.
- **Dependencies**: 80 packages, 9 chosen directly for JARVIS (`requirements.in`; `truststore`, already installed, became the ninth for Weather) and a few for the checks (`requirements-dev.in`).
- **Off-disk backups** (planned, see section 5): a new copy of the data outside this Mac.
- **Outside data** (Weather, section 5): replies from Open-Meteo, read by JARVIS's code, and
  the places asked about, sent to it.

## 4. Controls in place today

Each of these is in the code or the system and has been checked.

| Control | Protects against |
|---|---|
| FileVault (whole-disk encryption) is on | A stolen or lost Mac while it is off or locked. Does **not** protect anything while I am logged in. |
| Screen locks on sleep, password to wake | Someone using the Mac while I am away. Gap: the minutes before it sleeps. Habit: lock it when stepping away. |
| Server listens on `127.0.0.1` only | Everything on the network. |
| `TrustedHostMiddleware` allows only `127.0.0.1` and `localhost` | DNS rebinding (a website pretending to be this Mac). |
| JSON endpoints refuse `text/plain` bodies (pinned by a test) | Other websites driving `/chat`, `/confirm` or `/tasks`. |
| Every POST whose `Origin` is not JARVIS's own address is refused with 403, before any work (`server.py`, pinned by tests) | Other websites making JARVIS act or work, such as running Whisper through `/transcribe`. A second, independent lock on the JSON endpoints. Shown with `experiments/attack_page.html`: before, "transcribed 32044 bytes"; after, 403. |
| Outside requests go only to three fixed HTTPS addresses in `config.py`, built by code, through one function (`weather._get`), with redirects refused, certificates checked against macOS's own list (`truststore`), a 5 s limit on connecting and on each wait for data (not on the whole request), a 1 MB cap and coordinates rounded to 2 decimals (pinned by tests) | JARVIS being sent anywhere else, by the model or by a reply; someone between this Mac and the service pretending to be it. Checked live: an expired certificate and a wrong host name were refused (CHANGELOG section 56). |
| Outside names (places, regions, countries) are cleaned of control and invisible characters and cut to 60 characters before use (`weather.clean`) | Odd or hidden text from a reply reaching the page or, later, the model. |
| Every response carries a Content Security Policy (`server.py`, pinned by tests): only JARVIS's own scripts, styles, images, fonts and connections; audio also from `blob:` and `data:`; no plug-ins; never inside another site's page. (Except a crash's plain-text 500 reply, which has nothing to protect.) | Injected code running or sending data to another site, and clickjacking (a site hiding JARVIS under its own buttons so a click lands on Confirm). Checked in a demo: an inline script, an inline style, `eval`, a fetch to another site and a frame were all blocked (CHANGELOG section 55). |
| Deletes and edits only through a confirmation card and `POST /confirm` | The model deleting or changing events by itself. |
| Input limits (upload size, text length, date ranges, calculator) | Requests that use up memory or time. |
| Every SQL value goes through `?` parameters | SQL injection. |
| Calculator parses with `ast`, never `eval` | Running arbitrary code through arithmetic. |
| Pinned dependency versions, and a fingerprint (hash) of every file, checked on install (`--require-hashes`, also in CI) | A bad new release being installed without my knowing, and a file being swapped on PyPI or on the way. CHANGELOG section 49. |
| Whisper loads offline (`HF_HUB_OFFLINE=1`, set in `config.py`, pinned by a test) | Whisper telling huggingface.co each time it starts, and the speech model changing without my knowing (a supply-chain risk): it changes only when I run the download in README. Checked: a real transcription contacts no host (CHANGELOG section 45). |
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

Time Machine was considered for the rest of the Mac and is not planned (my decision,
2026-10-27). JARVIS's own data is covered by the encrypted copies above.

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
  tool, can only ask. This protects integrity. Since section 35 of the CHANGELOG, JARVIS
  also offers a card when I mention a lasting preference in passing ("I love sushi"); the
  rule is the same, because the click is still mine.
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

### Outside data: Weather (Phase 5, item 6)

Weather is the first time JARVIS reads anything from the internet
(`docs/specs/2026-11-05-weather-space.md`, CHANGELOG section 56). Until then the rule was
"nothing leaves the Mac except the encrypted backup copy". The rule now is (my wording,
agreed for Sports and kept for Weather):

> Nothing personal leaves the Mac unencrypted, and only I hold the key. JARVIS may fetch public
> data over HTTPS from a short list of fixed addresses, written in code. Those requests carry
> only what the service needs to answer, and the model never chooses the address.

- **What goes out**, to Open-Meteo only: the words of a place search ("Paris"), and a place's
  coordinates rounded to 2 decimal places (about 1 km), the home place's included each time it
  is opened. The forecast is the same at that size, but it does not pinpoint a street.
- **What Open-Meteo sees and keeps**: the Mac's IP address, as every website does, and the
  requests. Its terms (read 2026-11-05) say its server logs "may contain sensitive information
  such as geographical coordinates" and are deleted after 90 days. Accepted (section 7): the
  requests name a place, not a person, and no account links them to me.
- **The address is never the model's choice.** The three addresses are fixed in `config.py`;
  code builds every request; redirects are refused. A new outside service needs my agreement
  and the same rules.
- **HTTPS is checked.** python.org's Python ships without a list of trusted certificate
  signers, so at first every request failed. `truststore` checks against macOS's own list, the
  one Safari uses (my choice), with both checks on. Turning the check off was never an option:
  anyone between the Mac and the service could then pretend to be it.
- **The log** records each request's host, time and outcome, never its address (which holds the
  place). What I say to JARVIS is logged as before, so a place I ask about by voice is in the
  log like any message.
- **Nothing new is stored**: the cache, the match ids and the place on screen live in memory
  only, so no weather data reaches `jarvis.db` or the backups.
- **Outside text and the model**: place, region and country names are the first outside text
  JARVIS shows. The model reads some: the spoken line after a confirm, and the results of
  `find_place` (place names) and `get_forecast` (the forecast facts). They hold only cleaned
  names (at most 60 characters) and numbers that code checked are real numbers, written into
  sentences by `weather.py`, nothing else from a reply (pinned by tests). Every value in a reply is read
  as a real number or as cleaned text, or treated as missing (`weather._num`, pinned by tests),
  so the page and the conversation never get raw reply text. Anything longer, such as news,
  needs its own prompt-injection design first.

## 6. Known gaps

In rough order of importance.

1. **Offsite backups depend on a habit.** Encrypted copies are in iCloud Drive (section 5),
   but only as recent as the last time I copied them by hand. Route A (a copy made when
   the server starts) would remove the habit; not tried yet.
2. **The log holds message text** (first 300 characters of each message, and tool inputs
   and results), in up to 6 MB of files and the terminal. The note tools and note cards
   are logged as lengths only (section 5), but a message such as "remember that ..." is
   logged like any other: a known trade-off for being able to debug.
3. **Closed (CHANGELOG section 36):** `/transcribe` had no `Origin` check, so any website
   open in the browser could make JARVIS run Whisper. Every POST now checks `Origin`.
4. **Files are readable by group and others** (`-rw-r--r--`). Low risk while I am the only
   user, but `chmod 600` on the files and `700` on the folders is free.
5. **Closed (CHANGELOG section 49):** dependencies were pinned by version, not by hash.
   Every file now has its fingerprint in the lock files and is checked on install. What
   this does not cover: a harmful *new* version, which gets new fingerprints when I choose
   to upgrade. So an upgrade is a decision (`--upgrade-package`), never automatic.
6. **No login and no HTTPS.** Acceptable only while the server stays on `127.0.0.1`.

## 7. Accepted risks

- **Software running as me can read `jarvis.db`.** JARVIS has to read it, so anything
  running as me can too. Encrypting the database would not change this, because the key
  would also be on the Mac. The controls are FileVault, installing little, and pinned
  versions.
- **AI coding tools can read personal data in this folder.** Accepted because I approve
  what they run and CLAUDE.md sets the rules.
- **Open-Meteo sees the Mac's IP address and the places I ask about**, and keeps its logs up to
  90 days (section 5, Outside data). Accepted: a place, not a person, with coordinates rounded
  to about 1 km.

## 8. When to revisit

- Before Phase 6 (anything leaving `127.0.0.1`): the network becomes an attack surface, and
  a login and HTTPS are needed first. The `Origin` check compares against the address the
  request was sent to; HTTPS or a new address (Tailscale) means checking it again.
- Before adding a tool that reads outside content (news, web, sports): prompt injection
  becomes real. Weather's short place names are handled (section 5, Outside data); longer
  outside text needs its own design.
- Before adding any outside service: it joins the fixed list only with my agreement and the
  same rules (section 5, Outside data).
- If JARVIS is ever asked to hold something more sensitive than it does today.
- If someone else starts using this Mac.
