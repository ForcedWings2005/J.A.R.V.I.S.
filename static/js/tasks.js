// ---------- Tasks ----------
async function loadTasks() {
  const res = await fetch('/tasks');
  const data = await res.json();
  const box = document.getElementById('tasks');
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
      due.className = 'due';
      due.textContent = t.due;
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

