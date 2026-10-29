# Spaces, stage 4: the transition — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Changing space plays the access sequence for the whole space ("ACCESSING WORK", the
bar, "ACCESS GRANTED", the panels beam in, the orb glides into the dock); going back to Home
reverses it.

**Left out, by the owner's choice (2026-10-29):** the tilt stays as it is, Work's panels
included ("I like the lean"; deferred from stage 2's review). Phone width is not checked: a
phone version would more likely be the orb with the chat, perhaps able to pull up a panel,
and is a design for later.

**Architecture:** All of it lives in the motion layer, like section 42: `motion.js` wraps
`switchSpace` the way it wraps `focusPanel`, reusing the frame, bar, shockwave, skip and
safety-timeout helpers that already exist. The real switch is still `spaces.js`'s
`switchSpace`, called once in the middle of the sequence; without `motion.js` (or with Reduce
motion) switching is instant, exactly as today. Each space can describe its own readout and
say when its content is drawn, through two optional fields on `registerSpace`, so a new space
gets the sequence without editing `motion.js`'s logic.

**Tech Stack:** plain scripts sharing globals, CSS keyframes, the Web Animations API (already
used by `motion.js`). No Python change, no new dependency, no build step.

**Spec:** `docs/specs/2026-10-27-spaces-and-work.md` (stage 4 of its Build order; "Moving
between spaces", the Transition line; "Testing", In a browser). Background: CHANGELOG
section 42 (the access sequence for a panel).

## Global Constraints

- Transition (spec, verbatim): "the access sequence (section 42) for a whole space:
  "ACCESSING WORK", the bar, "ACCESS GRANTED", the panels beam in, and the orb glides into the
  dock. Back to Home reverses it. A click or Escape skips it; Reduce motion makes it instant."
- `motion.js` only wraps existing functions; every class it adds starts with `fx-`.
- The real switch stays in `spaces.js` (`switchSpace`): history, `leave`/`enter`, the header
  names and `data-space` are unchanged. Turning `motion.js` off leaves switching working.
- Every stage that waits on an animation has a safety timeout (`pause(...)` in a race), so a
  hidden tab, where browsers pause animations, cannot leave `seq` set.
- Opening the page at `/#work` shows Work at once, with no sequence (the boot sequence is the
  page's opening).
- The conversation, voice and a waiting confirmation card carry on through a change of space:
  `.center` is never hidden or rebuilt, only the orb is animated.
- No Python file changes, so the prompt is unchanged and no eval is needed; `ruff` and
  `pytest` must still pass (521).

## Review Focus

1. Changing space while a Home panel is open (Schedule focused, its calendar drawn): the panel
   closes, Home's calendar is emptied, Work's calendar opens in week view (Task 1, check 5).
2. A voice switch (`switchSpaceWhenFree`) arriving while a panel's or a space's sequence plays:
   it happens once, after the sequence ends (Task 1, check 6).
3. A hidden tab, where `animate()` never reports its end: the sequence still finishes and `seq`
   goes back to `null` within a few seconds (Task 1, check 7).
4. Pressing 1 and 2 quickly, or clicking a space name mid-sequence: one change at a time, and at
   the end `currentSpace`, `body.dataset.space`, the lit name and the address all agree
   (Task 1, check 4).

---

### Task 1: The access sequence for a whole space

**Files:**
- Modify: `static/js/motion.js` (a new block "Spaces: the access sequence for a whole space"
  after "Screens: the access sequence"; `STAGGER_ITEMS` unchanged)
- Modify: `static/css/motion.css` (a new block after "Screens"; the chip may charge)
- Modify: `static/js/spaces.js` (the `spaces` comment lists the two new optional fields; the
  `seq` guard's comment says a space change also sets it)
- Modify: `static/js/space-work.js` (`ready` and `readout` in its `registerSpace`)
- Create (scratch, not committed): the demo launcher in this session's scratchpad, as in
  stages 1–3 (`demo/run_demo.py`: made-up data, its own `demo.db`, backups and logs in its own
  folder, `JARVIS_DB` set before any import, port `8016`)

**Interfaces:**
- Consumes (`motion.js`, unchanged): `seq`, `stageWait(s, ms)`, `stageRace(s, promise)`,
  `skipSequence()`, `makeFrame(withReadout)`, `fillBar(s, frame, ready)`, `shockwave(rect)`,
  `box(rect)`, `once(node, cls, ms)`, `decode(target, ms)`, `stagger(container, selector)`,
  `pause(ms)`, `calm()`, `closeFocusPlain`; and from `spaces.js`: `spaces`, `currentSpace`,
  `spacesNav`, `switchSpace(name, opts)`.
- Produces:
  - `registerSpace` accepts two optional fields: `ready?: () => boolean` (true once the
    space's content is drawn; the bar waits for it, up to 3 s) and `readout?: () => string`
    (the line under the bar, from the real contents). Work's:
    `ready: () => !!document.querySelector('#work-cal .cbody > *') && !!document.querySelector('#work-day .day-lines')`
    (the error message "Couldn't load your day" is also a `.day-lines`, so a failed `/day`
    still counts as drawn);
    `readout` → `'<open> OPEN · <dated> DEADLINES'`, counting `#work-tasks .task:not(.done)`
    and, among those, the ones with a `.due`.
  - In `motion.js`: `switchSpacePlain` (the original) and a wrapped
    `switchSpace(name, opts = {}) -> boolean`: `false` for an unknown name, the current space,
    or while `seq` is set; instant (`switchSpacePlain`) when `calm()` or while the page is
    still starting (a `pageStarting` flag cleared by `motion.js`'s own `DOMContentLoaded`
    listener, which runs after `spaces.js`'s); otherwise starts `changeSpace(name, opts)` and
    returns `true`.
  - CSS: `body.fx-leaving` (Home's `.col` and `.timeline` play `fx-depart`: to opacity 0,
    `scale(.95)`, `blur(3px)`, 0.3 s, forwards); `.fx-return` (Home's columns come back:
    `fx-return`, the same values as a `from`, 0.45 s); `.space-chip.fx-charge` uses the
    existing `fx-charge` keyframes.

- [ ] **Step 1: Write the browser checks (they fail now)**

  Each runs in the demo at 1440x900 with `javascript_tool`, starting in Home with no panel
  open. A small sampler records state over time:
  ```js
  window.sample = (ms) => new Promise(r => setTimeout(() => r({
    seq: !!seq, space: currentSpace, data: document.body.dataset.space, hash: location.hash,
    lit: document.querySelector('.space-chip.on')?.dataset.space,
    frame: document.querySelector('.fx-frame .fx-title')?.dataset.text || null,
    hidden: document.getElementById('space-work').classList.contains('fx-hidden'),
    leaving: document.body.classList.contains('fx-leaving') }), ms));
  ```
  1. Home → Work: `switchSpace('work')`, then samples at 100, 1300 and 3500 ms.
     Expected: at 100 `{ seq: true, space: 'home', leaving: true }`; at 1300
     `{ seq: true, space: 'work', frame: 'ACCESSING WORK', hidden: true }`; at 3500
     `{ seq: false, space: 'work', data: 'work', hash: '#work', lit: 'work', frame: null,
     hidden: false, leaving: false }`. And the orb glided: right after the swap
     `document.querySelector('.orbwrap').getAnimations().length === 1`.
     Now: the switch is instant (`seq: false, space: 'work'` at 100).
  2. Work → Home: `switchSpace('home')`, samples at 100 and 2000 ms. Expected: at 100
     `{ seq: true, space: 'work' }` and every `#space-work .panel` has `fx-off`; at 2000
     `{ seq: false, space: 'home', hash: '', frame: null }` and no `.fx-frame` in the page.
  3. Skip: `switchSpace('work')`; at 600 ms dispatch Escape (`keydown` on `document`); sample
     at 700 ms → `{ seq: false, space: 'work', frame: null, hidden: false, leaving: false }`.
     The same with a real click on the transcript at 1200 ms instead of Escape.
     `switchSpace('home')`, real click at 300 ms → Home, `seq: false`, no `fx-leaving`.
  4. Review Focus 5: press `2`, then `1` at 200 ms, then `2` at 400 ms (real keys, the command
     box not focused) → one change; at 4000 ms `space`, `data`, `lit` and `hash` agree.
  5. Review Focus 1: in Home, click Schedule, wait 3 s, press `2` → at 4000 ms Work is shown,
     `focused === null`, `#cal` has no children, `cal.view === 'week'`, `#work-cal .cbody`
     has children, no `fx-receding` on `body`.
  6. Review Focus 2: in Home, click To-do; at 100 ms call `switchSpaceWhenFree('work')` → at
     5000 ms `space: 'work'`, the To-do screen closed, `seq: false`. Then in Work call
     `switchSpace('home')` and at 100 ms `switchSpaceWhenFree('work')` → at 6000 ms
     `space: 'work'`, `seq: false`.
  7. Review Focus 3: `const real = Element.prototype.animate; Element.prototype.animate =
     function (...a) { const x = real.apply(this, a); Object.defineProperty(x, 'finished',
     { value: new Promise(() => {}) }); return x; };` then `switchSpace('work')` → at 5000 ms
     `seq: false, space: 'work', frame: null`; restore `animate`; the same for
     `switchSpace('home')`.
  8. Reduce motion: switch it on (real click), `switchSpace('work')` → at once (no wait)
     `space: 'work'` and no `.fx-frame`; back to Home; switch it off.
  9. Load `/#work` (fresh page) → at 300 ms `space: 'work'`, `seq: false`, no `.fx-frame`.

- [ ] **Step 2: Implement the CSS** (`motion.css`, a block "Spaces: the access sequence for a
  whole space")

  `fx-depart` and `fx-return` keyframes and the rules in Interfaces; `.space-chip.fx-charge`
  added to the existing `.panel.fx-charge` rule.

- [ ] **Step 3: Implement `ready` and `readout` in `space-work.js`, and the comments in
  `spaces.js`** (values in Interfaces)

- [ ] **Step 4: Implement the sequence in `motion.js`**

  `changeSpace(name, opts)` follows section 42's `openScreen`: each stage awaits
  `stageWait`/`stageRace` (the latter raced with a `pause` safety timeout), and `if (s.skip)
  return finish();` after each one. The order:

  ```
  s = seq = { skip: false }; from = the current space object; to = the new one
  if (focused) { closeFocusPlain(); body.classList.remove('fx-receding'); }
  chip(name) charges (once 'fx-charge') and sends a shockwave from its rect
  1. Leave:  Home    → body.fx-leaving, wait 300
             a space → its panels get fx-off, wait 260; a frame (no readout) shrinks from
                       the section's rect into chip(from.name), 420 ms (safety 800);
                       remove the frame
  2. Swap:   measure the orb (.orbwrap), set its style.transition = 'none';
             swapSpace(name, opts); if to.section, add fx-hidden to it in the same task;
             measure the orb again, restore its transition, and animate it from the old
             box to the new one (translate + scale, transform-origin 0 0, 700 ms,
             cubic-bezier(.2,.8,.2,1)); remove fx-leaving
             to Home → finish()
  3. Enter:  frame (with readout) flies from chip(name) to the section's rect, 550 ms
             (safety 900); title 'ACCESSING ' + to.title, line to.readout?.() || '';
             fillBar(s, frame, ready) where ready polls to.ready every 30 ms, giving up at 3 s
             (no ready → at once); 'ACCESS GRANTED', fx-granted, wait 320; finish()
  finish(): remove any frame; swap if not swapped yet; remove fx-leaving and the old panels'
            fx-off; to Home → once(.col and .timeline, 'fx-return', 500) and decodeTitles();
            to a space → remove fx-hidden; each of its panels gets once 'fx-reveal' (900) and,
            at 420 ms, 'fx-glitch' (450); decode each panel's title;
            stagger(section, STAGGER_ITEMS + ', .deadline, .day-line') at 200 ms;
            seq = null
  ```
  - `swapSpace(name, opts)`: `spaces.js` refuses while `seq` is set, and this sequence is the
    one setting it, so it sets `seq = null`, calls `switchSpacePlain(name, opts)`, and puts
    `seq` back in a `finally`.
  - `chip(name)`: `spacesNav.querySelector('[data-space="' + name + '"]')`.
  - The existing wrapped `closeFocus` already turns Escape into `skipSequence()` while `seq` is
    set and not closing; the capture-phase click handler already skips on any click. Neither
    changes; `seq` here never has `closing`.

- [ ] **Step 5: Run the browser checks**

  - Step 1's checks 1–9 → as expected.
  - A screenshot at 1440x900 at each stage of check 1 (leave, frame flying, ACCESSING, ACCESS
    GRANTED, revealed) and of check 2, to look at by eye: the orb lands in the dock, nothing
    flashes, Home's columns come back.
  - A chat during the sequence: type "hello" while the bar fills (the click on the box skips
    the sequence) → the reply streams in the dock. With Ollama running, "let's get some work
    done" from Home → the sequence plays while the reply streams, then "take me back home".
  - `read_console_messages` with `onlyErrors` → none.

- [ ] **Step 6: Run the Python checks and commit**

  `ruff check . && python -m pytest -q` → `All checks passed!`, `521 passed`.
  ```bash
  git add static/js/motion.js static/css/motion.css static/js/spaces.js static/js/space-work.js
  git commit -m "Play the access sequence when changing space, and reverse it going home"
  ```

---

### Task 2: Docs

**Files:**
- Modify: `CHANGELOG.md` (section 53: what the transition does, the two new optional
  `registerSpace` fields, the owner's two choices (the tilt stays; phone width left for a
  later design), what was checked in the demo and what was not; the Status table: stage 4
  done, Safari not yet checked)
- Modify: `CLAUDE.md` (the `static/` row: `motion.js` also wraps `switchSpace`; a space may give
  `ready` and `readout`)
- Modify: `README.md` (only if it describes switching spaces: one sentence that a change of
  space animates, and that Reduce motion makes it instant)
- Modify: `plan.md` (stage 4 done; version 1 of spaces complete; Sports next)
- Modify: `docs/specs/2026-10-27-spaces-and-work.md` (Status: version 1 built, stages 1–4)

- [ ] **Step 1: Write the docs** (plain language, short sentences, as the files already are)

- [ ] **Step 2: Check and commit**

  `ruff check . && python -m pytest -q` → `All checks passed!`, `521 passed`.
  ```bash
  git add CHANGELOG.md CLAUDE.md README.md plan.md docs/specs/2026-10-27-spaces-and-work.md
  git commit -m "Document spaces, stage 4: the transition"
  ```
  Stop the demo server. The owner looks at it in Safari.
