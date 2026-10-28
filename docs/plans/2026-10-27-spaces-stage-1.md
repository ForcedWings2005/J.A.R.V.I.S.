# Spaces, stage 1: the structure — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Home and an empty Work space, switched by clicking a space name in the header, by
number keys, or by the address (`#work`, Back button), with JARVIS docked on the right in Work.

**Architecture:** One page. `<body data-space="...">` says which space is shown; layout rules in
CSS show Home's columns or the current space's `<section>`, and place the existing `.center`
(orb, conversation, card, command bar) in the centre on Home or in a dock on the right
elsewhere. No element is moved in the page, so chat, voice and the confirmation card keep
working. A small registry in `spaces.js` knows the spaces; each space registers itself.

**Tech Stack:** plain scripts sharing globals (no build step, no new dependency), CSS grid,
FastAPI serving `static/` as today.

**Spec:** `docs/specs/2026-10-27-spaces-and-work.md` (stage 1 of its Build order).

## Global Constraints

- No new dependency, no build step: plain `<script>` files loaded in order, sharing globals.
- Nothing in Python changes in this stage; `ruff check .` and `python -m pytest -q` must stay
  green (477 tests), and the existing test `test_every_file_the_page_loads_exists` must cover
  the new files.
- Home looks and behaves exactly as today, apart from the space names in the header.
- New CSS classes must not reuse names the page already uses (`chip` and `ghost` clashed
  before, CHANGELOG sections 40 and 42): the header names are `.space-chip`, the nav `.spaces`.
- Space names: `home` (key `1`, title `HOME`) and `work` (key `2`, title `WORK`).
- The address: `#work` for Work; no `#` part for Home. An unknown name in the address means
  Home.
- Number keys never act while typing in an `input` or `textarea`, or with Cmd, Ctrl or Alt held.
- Comments and docs: plain English, short sentences; match the file you are in.

## Review Focus

No JavaScript test runner exists (and adding one would be a new dependency), so the page is
checked in a demo with scripted browser checks, as for the motion layer. These are the inputs
most likely to bite that no single step's happy path covers; each has a check in its task:

1. Typing `1` or `2` in the command box (`#input`) types the digit and does not switch (Task 1).
2. Switching away from Home while a panel is expanded (the calendar open) closes it cleanly: no
   dim scrim left, `focused` is `null`, and Home looks normal on return (Task 1).
3. A confirmation card waiting on Home is still visible and its Confirm button still works in
   Work's dock (Task 2).
4. Reloading on `#work` opens Work; Back after a switch returns to the previous space; `#gym`
   opens Home (Task 1).
5. Pressing `2` in Work, or clicking the current space's name, does nothing (no new history
   entry, no flicker) (Task 1).

---

### Task 1: The registry, the header names, keys and the address

**Files:**
- Create: `static/js/spaces.js`
- Create: `static/js/space-work.js`
- Modify: `static/index.html` (a `<nav class="spaces" id="spaces">` in `<header>` right after
  `.readouts`; a `<section class="space" id="space-work" data-space="work" hidden>` after the
  last `.col`; script tags for `spaces.js` then `space-work.js` after `app.js`, before
  `motion.js`)
- Modify: `static/css/jarvis.css` (the `.spaces` nav and `.space-chip` buttons, in the header
  style: capsule glass like `.readouts .chip`, the current one `.on` in the accent colour)
- Create (scratch, not committed): `/private/tmp/claude-501/-Users-danterosalina-Developer-jarvis/2bd7a0ae-4b8a-4627-89d8-f518e03b7750/scratchpad/demo/run_demo.py`

**Interfaces:**
- Produces (globals in `spaces.js`):
  - `registerSpace(space)` where `space = { name: string, title: string, key: string,
    section: Element | null, enter?: () => void, leave?: () => void }`. Home is registered
    inside `spaces.js` with `section: null`.
  - `switchSpace(name: string, opts?: { fromAddress?: boolean }) -> boolean`: `false` and no
    change for an unknown name, the current space, or while the motion layer's opening
    sequence runs (`typeof seq !== 'undefined' && seq`; stage 4 replaces this guard);
    otherwise calls the old space's `leave`,
    sets `document.body.dataset.space`, shows only the new space's section (`hidden` on the
    others), marks the header name, calls the new space's `enter`, and, unless
    `opts.fromAddress`, pushes the address (`#work`, or the bare path for Home) with
    `history.pushState`. Returns `true`.
  - `currentSpace: string` (starts as `'home'`).
  - `spaceFromAddress() -> string`: `location.hash` without `#`, lower-cased, if registered;
    otherwise `'home'`.
- Produces (in `space-work.js`): `registerSpace({ name: 'work', title: 'WORK', key: '2',
  section: document.getElementById('space-work') })`. Stage 2 adds its panels and `enter`.
- Later stages rely on: stage 3 calls `switchSpace(name)` on a `space` event from `/chat`;
  stage 4's `motion.js` wraps `switchSpace` for the transition; `currentSpace` is sent with
  each message in stage 3.

- [ ] **Step 1: Write the demo launcher (scratch)**

  A copy of the earlier demo launcher (CHANGELOG section 42): sets `JARVIS_DB` to a `demo.db`
  next to itself before importing anything, points `config.BACKUP_DIR`,
  `config.BACKUP_ENCRYPTED_DIR` and `config.LOG_DIR` into its own folder, adds made-up events
  (a one-off today in the future, one tomorrow, a weekly series with `repeat_days`), four tasks
  (two with due dates, one done) and a note, then runs `uvicorn` on `127.0.0.1:8015` (a port
  no browser has a stale copy of). It serves the project's real `static/`.

- [ ] **Step 2: Write the browser checks (they fail now)**

  With the demo running, open `http://127.0.0.1:8015/?v=1` and run, in the page:

  ```js
  ({ registry: typeof switchSpace, chips: [...document.querySelectorAll('#spaces .space-chip')].map(b => b.textContent),
     space: document.body.dataset.space })
  ```
  Expected after Task 1: `{ registry: 'function', chips: ['1 HOME', '2 WORK'], space: 'home' }`.
  Now: `registry: 'undefined'`, `chips: []`.

- [ ] **Step 3: Implement `spaces.js`, `space-work.js`, the markup and the header style**

  - `spaces.js` registers Home, renders one `<button class="space-chip" data-space="...">`
    per space into `#spaces` (text: key, a space, title), clicking one calls
    `switchSpace(name)`.
  - Leaving Home calls `closeFocus()` first if a panel is expanded (`focused` is set). With
    the motion layer the close animates (about 0.7 s); that is fine, it finishes behind Work.
  - A space's `enter` or `leave` that throws is caught and logged with `console.error`; the
    switch still completes, so a broken space never stops Home (spec, When something goes
    wrong).
  - Keys: a `keydown` listener on `document`: if the key is a registered space's `key`, the
    target is not an `input`/`textarea`, and no Cmd/Ctrl/Alt is held, call
    `switchSpace(name)` and `preventDefault()`.
  - Address: `window.addEventListener('popstate', ...)` and `'hashchange'` both call
    `switchSpace(spaceFromAddress(), { fromAddress: true })`.
  - Start: on `DOMContentLoaded` (it fires after every script has run, so every space has
    registered), call `switchSpace(spaceFromAddress(), { fromAddress: true })`; if the
    address named an unknown space, replace it with the bare path (`history.replaceState`).
  - Set `data-space="home"` on `<body>` in `index.html` so the page is right before scripts run.

- [ ] **Step 4: Run the browser checks**

  Reload `http://127.0.0.1:8015/?v=2` and check, each in the page (expected values after the
  arrows):
  - Step 2's check → `{ registry: 'function', chips: ['1 HOME', '2 WORK'], space: 'home' }`.
  - Click the `2 WORK` button → `document.body.dataset.space === 'work'`, `location.hash ===
    '#work'`, `document.getElementById('space-work').hidden === false`, the `2 WORK` button
    has class `on`.
  - `history.back()` → `dataset.space === 'home'`, `location.hash === ''`.
  - Press `2` on the page → Work; press `1` → Home.
  - Review Focus 1: focus `#input`, type `12` → the box contains `12`, `dataset.space ===
    'home'`.
  - Review Focus 5: in Work, `history.length` before and after pressing `2` and clicking
    `2 WORK` → unchanged; `switchSpace('work') === false`.
  - Review Focus 2: on Home click the Schedule panel, wait 3 s (the opening sequence ends),
    press `2`, wait 1 s → `focused === null`,
    `document.body.classList.contains('has-focus') === false`; press `1` → the Schedule panel
    is not `.focused`.
  - During an opening sequence: click the To-do panel and press `2` within 0.3 s →
    `dataset.space === 'home'` (the key is ignored), and after 3 s the panel is open as usual.
  - A broken space: `registerSpace({ name: 'broken', title: 'BROKEN', key: '9', section: null,
    enter() { throw new Error('boom'); } })`, then `switchSpace('broken')` → returns `true`
    and logs one error; `switchSpace('home')` → `true`, Home looks normal.
  - Review Focus 4: load `http://127.0.0.1:8015/?v=3#work` → Work; load `...?v=4#gym` →
    Home and `location.hash === ''`.
  - `read_console_messages` with `onlyErrors` → none.

- [ ] **Step 5: Run the Python checks and commit**

  Run: `ruff check . && python -m pytest -q` → `All checks passed!` and `477 passed`
  (`test_every_file_the_page_loads_exists` now also covers `spaces.js` and `space-work.js`).

  ```bash
  git add static/js/spaces.js static/js/space-work.js static/index.html static/css/jarvis.css
  git commit -m "Add spaces: a registry, header names, number keys and the address"
  ```

### Task 2: The dock and the empty Work space

**Files:**
- Create: `static/css/space-work.css` (linked in `index.html` after `motion.css`)
- Modify: `static/index.html` (the Work section's content: one `.panel` with the header
  `<div class="h"><span class="l">WORK</span></div>` and a `.muted` line "Your day, deadlines
  and the calendar come here in the next stage.")
- Modify: `static/css/jarvis.css` (the dock layout, Home hidden in other spaces, phone width)
- Modify: `static/css/motion.css` (ambient mode also dims `.space`)

**Interfaces:**
- Consumes: `document.body.dataset.space` and the `section.space` elements from Task 1.
- Produces: the layout rule stage 2 builds on: in any space other than Home, `body` is a grid
  of the header row over two columns, the space's section on the left
  (`grid-column: 1`) and the dock (`.center`) on the right (`grid-column: 2`,
  `minmax(300px, 360px)` wide); inside the section, panels are laid out by that space's own
  stylesheet.

- [ ] **Step 1: Write the browser checks (they fail now)**

  In Work at 1440x900:
  ```js
  const c = document.querySelector('.center').getBoundingClientRect(), s = document.getElementById('space-work').getBoundingClientRect();
  ({ dockRight: c.left > s.right - 1, dockWidth: Math.round(c.width), homeHidden: getComputedStyle(document.querySelector('.col')).display === 'none',
     timelineHidden: getComputedStyle(document.querySelector('.timeline')).display === 'none' })
  ```
  Expected after Task 2: `{ dockRight: true, dockWidth: 300..360, homeHidden: true, timelineHidden: true }`.

- [ ] **Step 2: Implement the dock layout and the Work section**

  - In `jarvis.css`, under `body:not([data-space="home"])`: hide `.col` and `.timeline`; set
    `grid-template-columns: minmax(0, 1fr) minmax(300px, 360px)` and
    `grid-template-rows: auto minmax(0, 1fr)`; the header spans both columns; `.space`
    in column 1, `.center` in column 2; the orb smaller in the dock (`.orbwrap` width
    `min(180px, 100%, 22vh)`).
  - `.space[hidden]` is `display: none`; a shown `.space` fills its cell and scrolls inside
    itself.
  - Phone width (inside the existing `@media (max-width:900px)`): one column; in a space the
    dock comes first (`.center` already has `order: -1`) and the section below.
  - `motion.css`: add `body.fx-ambient .space` to the ambient-mode selector that dims the
    columns.

- [ ] **Step 3: Run the browser checks**

  - Step 1's check at 1440x900 → as expected; a screenshot shows the empty Work panel on the
    left and the orb, conversation and command bar on the right.
  - Back on Home → the layout is today's (columns, timeline, orb in the centre): compare a
    screenshot with one taken before this task.
  - Review Focus 3: on Home call `showConfirm({ id: 'x', text: "Delete 'Dentist'?" })`, press
    `2` → `#confirm` is visible in the dock (`getBoundingClientRect().width > 0`, inside
    `.center`); then `hideConfirm()`.
  - In Work run `startExchange('test'); botEl.textContent = 'ok'; endExchange();` → the two
    lines are visible inside the dock (`#transcript` inside `.center`, its bounding box
    inside the dock's).
  - Phone width (375x812, reload): in Work, `.center` is above `#space-work`
    (`center.top < section.top`), no sideways scrolling
    (`document.documentElement.scrollWidth === innerWidth`).
  - Reduce motion on, switch spaces → no errors; ambient class on → `.space` dims.
  - `read_console_messages` with `onlyErrors` → none.

- [ ] **Step 4: Run the Python checks and commit**

  Run: `ruff check . && python -m pytest -q` → `All checks passed!` and `477 passed`.

  ```bash
  git add static/css/space-work.css static/index.html static/css/jarvis.css static/css/motion.css
  git commit -m "Dock JARVIS on the right in a space, and add an empty Work space"
  ```

### Task 3: Docs, then the owner's check

**Files:**
- Modify: `CHANGELOG.md` (new section 50, "Spaces, stage 1"; the file layout lists
  `spaces.js`, `space-work.js`, `space-work.css`, `docs/specs/`, `docs/plans/`; a Status row)
- Modify: `README.md` (in Run: the space names, keys `1`/`2`, `#work`)
- Modify: `CLAUDE.md` (the `static/` row: the script order now ends `app, spaces,
  space-work, motion`; `body[data-space]` and `registerSpace`)
- Modify: `plan.md` (a line under Phase 5 pointing to the spec and this plan)

**Interfaces:**
- Consumes: everything above. Produces: nothing new.

- [ ] **Step 1: Write the docs**

  Section 50 says what changed, why (the spec), what was checked in the demo (each Review
  Focus line with its result) and what was not (Safari, the real data). Copy the real
  results; never write a check that did not run.

- [ ] **Step 2: Run the Python checks and commit**

  Run: `ruff check . && python -m pytest -q` → `All checks passed!` and `477 passed`.

  ```bash
  git add CHANGELOG.md README.md CLAUDE.md plan.md
  git commit -m "Document spaces, stage 1"
  ```

- [ ] **Step 3: The owner checks it in Safari**

  Stop the demo server. Ask the owner to try it in Safari on the demo or their own server:
  switch by click, `1`/`2`, Back, reload on `#work`; a card while switching. Push only when
  they say so.
