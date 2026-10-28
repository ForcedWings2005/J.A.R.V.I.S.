// ---------- The Work space (docs/specs/2026-10-27-spaces-and-work.md) ----------
// The calendar opens here in week view while Work is shown, and goes back to Home's
// Schedule panel (year view) on leaving. The to-do list is drawn here by tasks.js. The strip
// and Deadlines come from GET /day, worked out by workday.py: nothing here does date sums.
registerSpace({
  name: 'work', title: 'WORK', key: '2', section: document.getElementById('space-work'),
  enter() { openCal(document.getElementById('work-cal'), 'week'); loadDay(); },
  leave() { closeCal(); },
});

const dayBox = document.getElementById('work-day');
const deadlinesBox = document.getElementById('work-deadlines');

async function loadDay() {
  let summary;
  try {
    const res = await fetch('/day');
    if (!res.ok) throw new Error('day ' + res.status);
    summary = await res.json();
  } catch (e) {
    showDayLines(["Couldn't load your day"]);
    deadlinesBox.textContent = '';
    deadlinesBox.appendChild(h('div', 'muted', "Couldn't load your day"));
    return;
  }
  drawDay(summary);
}

// 'a', 'a and b', 'a, b and c'
function inList(parts) {
  return parts.length < 2 ? parts.join('') : parts.slice(0, -1).join(', ') + ' and ' + parts.at(-1);
}

function dayLines(s) {
  const free = s.free.length
    ? 'Free ' + inList(s.free.map(g => g.end === s.day_end
      ? 'after ' + fmtTime(g.start) : fmtTime(g.start) + ' – ' + fmtTime(g.end)))
    : 'No free time left today';
  const next = s.next
    ? s.next.title + ' at ' + fmtTime(s.next.time) + ', ' + inWords(s.next.in_minutes)
    : 'Nothing else on today';
  const d = s.deadlines[0];
  let deadline = 'No deadlines';
  if (d) {
    if (d.state === 'overdue') deadline = d.title + ' is overdue';
    else if (d.days_left === 0) deadline = d.title + ' due today';
    else if (d.days_left === 1) deadline = d.title + ' due tomorrow';
    else deadline = d.title + ' due ' + friendlyDue(d.due, false).text;
  }
  return [free, next, deadline];
}

function showDayLines(lines) {
  dayBox.querySelector('.day-lines')?.remove();
  const box = h('div', 'day-lines');
  for (const line of lines) box.appendChild(h('div', 'day-line', line));
  dayBox.appendChild(box);
}

function drawDay(s) {
  showDayLines(dayLines(s));
  deadlinesBox.textContent = '';
  if (!s.deadlines.length) { deadlinesBox.appendChild(h('div', 'muted', 'No deadlines')); return; }
  s.deadlines.forEach((d, i) => {
    const row = h('div', 'deadline');
    row.dataset.state = d.state;
    const top = h('div', 'dl-top');
    top.appendChild(h('span', 'dl-title', d.title));
    if (i === 0) top.appendChild(h('span', 'dl-next', 'NEXT UP'));
    top.appendChild(h('span', 'dl-when', friendlyDue(d.due, false).text));
    // The bar fills over the last DEADLINE_WINDOW_DAYS days; overdue is full
    const fill = d.state === 'overdue' ? 1
      : Math.max(0, Math.min(1, (s.deadline_window_days - d.days_left) / s.deadline_window_days));
    const bar = h('div', 'dl-bar');
    const level = document.createElement('i');
    level.style.width = Math.round(fill * 100) + '%';
    bar.appendChild(level);
    row.append(top, bar);
    deadlinesBox.appendChild(row);
  });
}

// Keep it current: after anything changes the to-do list or the calendar, and every minute
// (free time shrinks as the day goes on). Wrapped like motion.js does: the original runs first.
const loadTasksBeforeWork = loadTasks;
loadTasks = async () => { await loadTasksBeforeWork(); if (currentSpace === 'work') loadDay(); };
const loadEventsBeforeWork = loadEvents;
loadEvents = async () => { await loadEventsBeforeWork(); if (currentSpace === 'work') loadDay(); };
setInterval(() => { if (currentSpace === 'work') loadDay(); }, 60000);
