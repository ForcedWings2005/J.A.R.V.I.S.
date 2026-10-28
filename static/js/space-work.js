// ---------- The Work space (docs/specs/2026-10-27-spaces-and-work.md) ----------
// The calendar opens here in week view while Work is shown, and goes back to Home's
// Schedule panel (year view) on leaving. The to-do list is drawn here by tasks.js.
registerSpace({
  name: 'work', title: 'WORK', key: '2', section: document.getElementById('space-work'),
  enter() { openCal(document.getElementById('work-cal'), 'week'); },
  leave() { closeCal(); },
});
