# Weather, stage 1: the Content Security Policy — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every response from JARVIS carries a strict Content Security Policy, so the page can
run only its own files, talk only to JARVIS, and never be shown inside another website.

**Architecture:** One constant and one small HTTP middleware in `server.py`, defined last so it
wraps every other middleware and its header also lands on refused requests (403 from the
`Origin` check, 400 from `TrustedHostMiddleware`). Tests in `tests/test_server.py` pin the exact
value and the paths that carry it, and two scans of `static/` catch future code the policy would
block. Then a demo in the browser shows that the page still works and that the policy really blocks.

**Tech Stack:** FastAPI/Starlette middleware, pytest with `TestClient`. No new dependency, no
change to the page, no prompt change (so no eval).

**Spec:** `docs/specs/2026-11-05-weather-space.md` (sections "The Content Security Policy",
"Testing" (the CSP line), "Build order" stage 1).

## Global Constraints

- The policy, exactly (spec, one line in the header, separated by `; `):
  `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; connect-src 'self'; media-src 'self' blob: data:; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'`
- No `'unsafe-inline'`, no `'unsafe-eval'`, no outside address. Loosening any part is a security
  change: stop and ask the owner (CLAUDE.md, Safety boundaries).
- "Sent with every response ... on every path" (spec).
- The existing locks stay separate and unchanged: `TrustedHostMiddleware`,
  `refuse_other_websites`, the `text/plain` refusal, `check_page_files_again`. Their tests are
  not edited.
- The demo never touches the real `jarvis.db`, `backups/` or `logs/`: `JARVIS_DB` is set before
  any import, and the backup and log folders are pointed at the demo's own folder.
- Commit on `weather-space` after each task that works. Never on `main`. Do not push.

## Review Focus

1. **A refused request** (403 from another `Origin`, 400 from another host name) must carry the
   header too. Starlette only adds it if the CSP middleware is the outermost one. Pinned by
   `test_refused_requests_carry_the_security_policy` (Task 1).
2. **The streamed `/chat` reply** must carry it. A `StreamingResponse` sends its headers before
   the body, so this is checked explicitly: `test_streamed_chat_carries_the_security_policy`
   (Task 1).
3. **A missing file** (404 from `/static`) must carry it: `test_missing_files_carry_the_security_policy`
   (Task 1).
4. **Inline code added to `index.html` later** (a `<script>` without `src`, a `<style>`, a
   `style=` or `on...=` attribute) would silently stop working under the policy. Pinned by
   `test_the_page_has_nothing_inline` (Task 1).
5. **Script code the policy blocks** (`eval(`, `new Function`, `setAttribute('style'`,
   `insertAdjacentHTML`, `javascript:`) added later, such as in the Weather scripts, would fail
   only in the browser. Pinned by `test_the_scripts_use_nothing_the_policy_blocks` (Task 1).

Not covered by any automated test: a server crash (500) comes from Starlette's outermost
error handler, as plain text, without the header. Accepted: it has no page to protect. Also
not covered: how Safari applies the policy, which the owner checks (Task 2).

---

### Task 1: The policy header, and the tests that pin it

**Files:**
- Modify: `server.py`: the constant `CONTENT_SECURITY_POLICY` next to `READ_ONLY` (line 67),
  and a new middleware after `check_page_files_again` (lines 127–133), as the last
  `@app.middleware` in the file.
- Test: `tests/test_server.py`: new tests after `test_json_sent_as_plain_text_is_refused`
  (line 116), the other locks' tests.

**Interfaces:**
- Consumes: the `client` fixture (`TestClient(server.app, base_url="http://127.0.0.1")`), and
  `model` and `FakeModel`/`say` from `fakes.py`, as `test_chat_streams_events` uses them.
- Produces: `server.CONTENT_SECURITY_POLICY: str`, the exact value under Global Constraints;
  `async def add_security_policy(request, call_next)`, which sets
  `response.headers["Content-Security-Policy"]`.

- [ ] **Step 1: Write the failing tests**

The policy is written out in full in the test, not read from `server`, so a quiet edit to the
constant fails the test:

```python
POLICY = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; "
          "font-src 'self'; connect-src 'self'; media-src 'self' blob: data:; "
          "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")

@pytest.mark.parametrize("path", ["/", "/static/js/app.js", "/static/css/jarvis.css", "/tasks"])
def test_every_response_carries_the_security_policy(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers["content-security-policy"] == POLICY

def test_refused_requests_carry_the_security_policy(client):
    other_site = client.post("/reset", json={}, headers={"Origin": "http://evil.example"})
    assert other_site.status_code == 403
    assert other_site.headers["content-security-policy"] == POLICY
    other_host = TestClient(server.app, base_url="http://evil.example").get("/")
    assert other_host.status_code == 400
    assert other_host.headers["content-security-policy"] == POLICY

def test_missing_files_carry_the_security_policy(client):
    response = client.get("/static/js/no-such-file.js")
    assert response.status_code == 404
    assert response.headers["content-security-policy"] == POLICY

def test_streamed_chat_carries_the_security_policy(client, model):
    model(say("Hello."))
    response = client.post("/chat", json={"message": "hello"})
    assert response.status_code == 200
    assert response.headers["content-security-policy"] == POLICY

def test_the_page_has_nothing_inline():
    """The policy forbids inline code, so it would silently stop working (spec, CSP)."""
    page = (config.STATIC_DIR / "index.html").read_text()
    assert re.search(r"<script(?![^>]*\bsrc=)[^>]*>", page) is None
    assert "<style" not in page
    assert re.search(r"\sstyle\s*=", page) is None
    assert re.search(r"\son[a-z]+\s*=", page) is None

def test_the_scripts_use_nothing_the_policy_blocks():
    blocked = ["eval(", "new Function", "setAttribute('style'", 'setAttribute("style"',
               "insertAdjacentHTML", "javascript:"]
    for script in (config.STATIC_DIR / "js").glob("*.js"):
        text = script.read_text()
        for word in blocked:
            assert word not in text, f"{script.name} uses {word}"
```

`re` is a new import at the top of the test file. `ResetRequest` is empty, so `json={}` is a
valid body; the 403 comes before the body is read either way. Both scans were tried against
today's `static/` on 2026-11-05 and find nothing.

- [ ] **Step 2: Run them to make sure the right ones fail**

Run: `python -m pytest -q tests/test_server.py -k "security_policy or nothing_inline or policy_blocks"`
Expected: the five header tests fail with `KeyError: 'content-security-policy'`, and
`test_the_page_has_nothing_inline` and `test_the_scripts_use_nothing_the_policy_blocks` pass
(the page is already clean, as the spec found on 2026-11-05). Two passing here is correct:
they guard the future, not this change. Write in the ledger that they passed before the code
existed, and why.

- [ ] **Step 3: Write the constant and the middleware in `server.py`**

- `CONTENT_SECURITY_POLICY` next to `READ_ONLY`, built from one string per directive joined by
  `"; "`, so each part can carry a short comment saying what it allows, e.g. `blob:` for the
  spoken reply (`voice.js`, `playBlob`), `data:` for the silent clip (`voice.js`, `SILENCE`),
  `frame-ancestors 'none'` against clickjacking. It lives in `server.py`, not `config.py`:
  it is a security lock like `READ_ONLY`, not a setting to tune. That is a deliberate exception
  to "settings belong in `config.py`", and the comment says so.
- `add_security_policy(request, call_next)`: awaits `call_next(request)` and sets the header on
  every response, whatever its path or status. Docstring: why it must be defined last. Each
  middleware added wraps the ones before it, so the last is the outermost and also sees the
  responses that `refuse_other_websites` and `TrustedHostMiddleware` make without calling
  further in. The spec section is named.

- [ ] **Step 4: Run the tests to make sure they pass, then everything**

Run: `python -m pytest -q tests/test_server.py -k "security_policy or nothing_inline or policy_blocks"`
Expected: all 10 pass (4 parametrized + 6). Then run `ruff check .` and `python -m pytest -q`.
Expected: ruff passes, and 531 tests pass (521 + 10).

- [ ] **Step 5: Commit**

```bash
git add server.py tests/test_server.py
git commit -m "Send a Content Security Policy with every response"
```

(Body: what the policy allows and blocks in two lines, the new test names, `531 passed`, and the
attribution line.)

---

### Task 2: The demo check in the browser

No file in the repo changes in this task unless something fails. If anything is blocked that
the page needs, **stop and tell the owner**: the fix would loosen the policy, which is the
owner's decision.

**Files:**
- Create (scratch, not committed): `demo/run_demo.py` in this session's scratchpad. It sets
  `os.environ["JARVIS_DB"]` to the demo's own `demo.db` **before importing anything from the
  project**. Then it sets `config.BACKUP_DIR`, `config.BACKUP_ENCRYPTED_DIR` and `config.LOG_DIR`
  to folders inside the demo folder, before `backup_db` or `server` is imported (`backup_db`
  copies them into its own names at import). It adds made-up events for this week through
  `jcal` and three made-up tasks through `tasks`, then runs `uvicorn.run(server.app,
  host="127.0.0.1", port=8016)`. Run it with the project folder on `sys.path` and as the
  working directory, with the venv's Python, in the background.

**Interfaces:**
- Consumes: Task 1's header on every response.
- Produces: the list of checks and their results, for CHANGELOG section 55 (Task 3).

- [ ] **Step 1: Start the demo and open it** at `http://127.0.0.1:8016`, 1440x900, in the
  built-in browser. Confirm `jarvis.db`'s modification time and the newest file in `backups/`
  have not changed (`ls -l` before and after).
- [ ] **Step 2: The header reached the browser.** In `javascript_tool`:
  `(await fetch('/')).headers.get('content-security-policy')`.
  Expected: the exact policy.
- [ ] **Step 3: No violations while loading.** Hard reload, wait for the boot sequence, then
  `read_console_messages` with pattern `Content Security Policy` and with `onlyErrors`.
  Expected: none.
- [ ] **Step 4: Record violations from here on.** Add a listener in `javascript_tool`:
  `window.__csp = []; document.addEventListener('securitypolicyviolation', e => __csp.push(e.violatedDirective + ' ' + e.blockedURI))`.
  After each check below, read `window.__csp`. Expected: `[]` every time.
- [ ] **Step 5: The page still works.**
  - **Calendar:** open the Schedule panel, then each view (day, week, month, agenda), and check
    the made-up events are drawn.
  - **Tasks:** tick and untick a task.
  - **Animations:** the panel access sequence; switching to Work and back (key 2, key 1);
    Reduce motion on and off.
  - **A chat reply:** one message with the real model. If Ollama is not running, write "not checked".
  - **Voice:** voice on, a short reply spoken. Expected: an `Audio` playing a `blob:` address,
    and the silent `data:` clip at unlock. If Kokoro cannot load, write "not checked".
- [ ] **Step 6: The policy really blocks.** Each one runs in `javascript_tool`:
  - An inline script: `const s = document.createElement('script'); s.textContent = 'window.__ran = 1'; document.body.append(s); window.__ran`.
    Expected: `undefined`, and `__csp` gains a `script-src` entry.
  - `eval('1 + 1')`. Expected: an `EvalError`.
  - `fetch('https://example.com')`. Expected: it rejects (blocked by `connect-src` before
    any request leaves), and `__csp` gains a `connect-src` entry.
  - Clear `__csp` afterwards.
- [ ] **Step 7: Framing is refused.** From a different origin page (`about:blank` in a new tab), try to
  put `http://127.0.0.1:8016/` in an `iframe`. Expected: the frame stays empty (blocked by
  `frame-ancestors`). If the built-in browser cannot show this, write "not checked".
- [ ] **Step 8: Stop the demo server** and remove nothing from the repo. Not checkable here:
  the microphone (`/transcribe` through `fetch`, covered by `connect-src 'self'`) and Safari.
  The owner checks both.

---

### Task 3: The docs

**Files:**
- Modify: `SECURITY.md` section 4: a new row after the `Origin` row. **Control:** "Every response
  carries a Content Security Policy (`server.py`, pinned by tests): only JARVIS's own scripts,
  styles, images, fonts and connections; audio also from `blob:` and `data:`; no plug-ins; never
  inside another site's page". **Protects against:** "Injected code running or sending data to
  another site, and clickjacking (a site hiding JARVIS under its own buttons). Checked in a demo:
  an inline script, `eval` and a fetch to another site were all blocked (CHANGELOG section 55)."
- Modify: `CLAUDE.md`, Safety and security boundaries: a bullet after the `Origin` bullet. "Every
  response carries the Content Security Policy in `server.py` (`CONTENT_SECURITY_POLICY`, the
  outermost middleware). The page may load and talk only to its own address, so it has no
  inline scripts or styles and no `eval`; `tests/test_server.py` pins the policy and scans
  `static/` for both. Loosening it needs the owner's agreement." Also add "the Content Security
  Policy" to `server.py`'s row in the file table.
- Modify: `CHANGELOG.md`: section `## 55. Weather, stage 1: a Content Security Policy`, in the
  style of section 53. Cover what a CSP is in two sentences, what each part allows and why
  (`blob:`, `data:`), the review-focus tests and why two passed before the code existed, the
  demo's checks with their real results, and what was not checked (Safari, the microphone,
  anything Step 5 or 7 marked "not checked"). Plan: this file; spec:
  `docs/specs/2026-11-05-weather-space.md`. Also a Status table row: "Content Security Policy
  (section 55) | Done; checked in a demo; not yet in Safari". Update the header's "last updated"
  date.

- [ ] **Step 1: Write the three edits** as above.
- [ ] **Step 2: Check every claim against the code and the demo.** The test names and counts,
  the line `CONTENT_SECURITY_POLICY` is on, and each demo result as observed. Then run
  `ruff check .` and `python -m pytest -q`.
  Expected: ruff passes, and 531 tests pass.
- [ ] **Step 3: Commit**

```bash
git add SECURITY.md CLAUDE.md CHANGELOG.md
git commit -m "Document the Content Security Policy (CHANGELOG section 55)"
```

Then report to the owner as CLAUDE.md asks, ending with the Safari check: open JARVIS in
Safari, open the Web Inspector console, use the calendar, voice and the microphone once, and
look for any "Content Security Policy" message.
