// ---------- Tasks ----------
// '2026-10-24' -> 'Tomorrow', 'Tue 27 Oct' or 'Overdue · Mon 19 Oct', for the to-do list
const TASK_DOWS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const TASK_MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
function friendlyDue(isoDate, done) {
  const [y, m, d] = isoDate.split('-').map(Number);
  const due = new Date(y, m - 1, d);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const days = Math.round((due - today) / 86400000);
  const name = TASK_DOWS[due.getDay()] + ' ' + due.getDate() + ' ' + TASK_MONTHS[due.getMonth()];
  if (days === 0) return { text: 'Today', late: false };
  if (days === 1) return { text: 'Tomorrow', late: false };
  if (days < 0) return { text: done ? name : 'Overdue \u00b7 ' + name, late: !done };
  return { text: name, late: false };
}

async function loadTasks() {
  const res = await fetch('/tasks');
  const data = await res.json();
  const box = document.getElementById('tasks');
  const open = data.tasks.filter(t => !t.done).length;
  document.getElementById('tasks-count').textContent = open + ' OPEN';
  box.innerHTML = '';
  if (data.tasks.length === 0) {
    const none = document.createElement('div');
    none.className = 'muted';
    none.textContent = 'No tasks yet';
    box.appendChild(none);
    return;
  }
  for (const t of data.tasks) {
    const label = document.createElement('label');
    label.className = 'task' + (t.done ? ' done' : '');
    label.dataset.id = t.id;
    label.addEventListener('click', e => e.stopPropagation());
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = t.done;
    cb.addEventListener('change', () => toggleTask(t.id, cb.checked));
    const name = document.createElement('span');
    name.className = 't';
    name.textContent = t.title;
    label.append(cb, name);
    if (t.due) {
      const due = document.createElement('span');
      const words = friendlyDue(t.due, t.done);
      due.className = 'due' + (words.late ? ' late' : '');
      due.textContent = words.text;
      due.title = t.due;
      label.appendChild(due);
    }
    box.appendChild(label);
  }
}

async function toggleTask(id, done) {
  await fetch('/tasks/' + id, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ done: done })
  });
  loadTasks();
}

