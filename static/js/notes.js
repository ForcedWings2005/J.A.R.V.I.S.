// ---------- Notes and memory ----------
// Read-only: notes are saved and forgotten through the chat and the confirmation card.
async function loadNotes() {
  const box = document.getElementById('notes');
  let data;
  try { data = await (await fetch('/notes')).json(); }
  catch (e) { box.textContent = 'Could not load notes.'; return; }
  box.innerHTML = '';
  if (data.notes.length === 0) {
    const none = document.createElement('div');
    none.className = 'muted';
    none.textContent = 'No notes yet. Say "remember that I like tea".';
    box.appendChild(none);
    return;
  }
  for (const n of data.notes) {
    const row = document.createElement('div');
    row.className = 'note';
    row.textContent = n.text;
    box.appendChild(row);
  }
}
