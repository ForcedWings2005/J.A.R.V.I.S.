"""The to-do list: tasks have a title and an optional due date, but no time of day."""
from datetime import datetime

from database import conn as db, lock
from tools import tool


def tasks_list() -> list:
    """For the To-do panel: open tasks first, then by due date."""
    with lock:
        rows = db.execute(
            "SELECT id, title, due, done FROM tasks "
            "ORDER BY done, due IS NULL, due, id LIMIT 50"
        ).fetchall()
    return [{"id": i, "title": t, "due": d, "done": bool(n)} for i, t, d, n in rows]


def set_task_done(task_id: int, done: bool) -> bool:
    """The panel's checkbox. Returns False if there is no such task."""
    with lock:
        cur = db.execute(
            "UPDATE tasks SET done = ? WHERE id = ?", (1 if done else 0, task_id)
        )
        db.commit()
        return cur.rowcount > 0


@tool("Add an item to the to-do list. Tasks have no time of day. Use add_event instead for anything with a specific time.",
      title={"type": "string"},
      due={"type": "string", "description": "Optional due date, YYYY-MM-DD"})
def add_task(title: str, due: str = "") -> str:
    title = title.strip()
    if not title:
        return "Error: the task needs a title."
    if due:
        try:
            datetime.strptime(due, "%Y-%m-%d")
        except ValueError:
            return "Error: due must be YYYY-MM-DD."
    with lock:
        dup = db.execute(
            "SELECT 1 FROM tasks WHERE done = 0 AND lower(title) = ?",
            (title.lower(),),
        ).fetchone()
        if dup:
            return f"Error: '{title}' is already on the list."
        db.execute("INSERT INTO tasks (title, due) VALUES (?, ?)", (title, due or None))
        db.commit()
    return f"Added task '{title}'" + (f", due {due}." if due else ".")


@tool("List the open items on the to-do list, with their due dates.")
def list_tasks() -> str:
    open_tasks = [t for t in tasks_list() if not t["done"]]
    if not open_tasks:
        return "No open tasks."
    parts = [t["title"] + (f" (due {t['due']})" if t["due"] else "") for t in open_tasks]
    return "Open tasks: " + "; ".join(parts)


@tool("Mark a to-do item as finished, matched by its title.",
      title={"type": "string"})
def complete_task(title: str) -> str:
    with lock:
        rows = db.execute(
            "SELECT id, title FROM tasks WHERE done = 0 AND instr(lower(title), ?) > 0",
            (title.lower(),),
        ).fetchall()
        if not rows:
            return f"Error: no open task matching '{title}'."
        if len(rows) > 1:
            names = "; ".join(name for _, name in rows)
            return f"Error: several tasks match ({names}). Ask the user which one."
        db.execute("UPDATE tasks SET done = 1 WHERE id = ?", (rows[0][0],))
        db.commit()
    return f"Marked '{rows[0][1]}' as done."
