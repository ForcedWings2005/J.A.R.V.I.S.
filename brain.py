import threading
import uuid
import ast
import math
import operator
import ollama
import config
import jcal
from database import conn as db, lock as db_lock
from datetime import datetime, timedelta

MODEL = config.MODEL
MAX_ROUNDS = config.MAX_ROUNDS

chat_lock = threading.Lock()

pending = {}
turn = {"confirm": None}

def delete_event(title: str, date: str = "", scope: str = "this") -> str:
    found = jcal.find_for_delete(title, date, scope)
    if isinstance(found, str):
        return found
    pid = uuid.uuid4().hex[:8]
    pending.clear()
    pending[pid] = found["action"]
    turn["confirm"] = {"id": pid, "text": found["text"]}
    return "Confirmation required. The event has NOT been deleted yet. Tell the user to confirm on screen."

def resolve_pending(pid: str, approve: bool) -> str:
    with chat_lock:
        action = pending.pop(pid, None)
        if action is None:
            return "That request has expired or was already handled."
        if approve:
            jcal.apply_delete(action)
            text = "Done. The event has been deleted."
        else:
            text = "Okay, I left it alone."
        messages.append({"role": "assistant", "content": text})
        return text

def tasks_list() -> list:
    with db_lock:
        rows = db.execute(
            "SELECT id, title, due, done FROM tasks "
            "ORDER BY done, due IS NULL, due, id LIMIT 50"
        ).fetchall()
    return [{"id": i, "title": t, "due": d, "done": bool(n)} for i, t, d, n in rows]

def add_task(title: str, due: str = "") -> str:
    title = title.strip()
    if not title:
        return "Error: the task needs a title."
    if due:
        try:
            datetime.strptime(due, "%Y-%m-%d")
        except ValueError:
            return "Error: due must be YYYY-MM-DD."
    with db_lock:
        dup = db.execute(
            "SELECT 1 FROM tasks WHERE done = 0 AND lower(title) = ?",
            (title.lower(),),
        ).fetchone()
        if dup:
            return f"Error: '{title}' is already on the list."
        db.execute("INSERT INTO tasks (title, due) VALUES (?, ?)", (title, due or None))
        db.commit()
    return f"Added task '{title}'" + (f", due {due}." if due else ".")

def list_tasks() -> str:
    open_tasks = [t for t in tasks_list() if not t["done"]]
    if not open_tasks:
        return "No open tasks."
    parts = [t["title"] + (f" (due {t['due']})" if t["due"] else "") for t in open_tasks]
    return "Open tasks: " + "; ".join(parts)

def complete_task(title: str) -> str:
    with db_lock:
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

def set_task_done(task_id: int, done: bool) -> bool:
    with db_lock:
        cur = db.execute(
            "UPDATE tasks SET done = ? WHERE id = ?", (1 if done else 0, task_id)
        )
        db.commit()
        return cur.rowcount > 0

OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv, ast.USub: operator.neg, ast.UAdd: operator.pos,
}
FUNCS = {
    "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "log": math.log, "log10": math.log10, "abs": abs, "round": round,
}
CONSTS = {"pi": math.pi, "e": math.e}
MAX_RESULT = 10 ** 300  # stops runaway numbers like (10**1000)**1000


class TooLarge(Exception):
    pass


def _check(value):
    if abs(value) > MAX_RESULT:
        raise TooLarge
    return value

def _eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.Name) and node.id in CONSTS:
        return CONSTS[node.id]
    if isinstance(node, ast.BinOp) and type(node.op) in OPS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 1000:
            raise TooLarge
        return _check(OPS[type(node.op)](left, right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in OPS:
        return OPS[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCS:
        return _check(FUNCS[node.func.id](*[_eval(a) for a in node.args]))
    raise ValueError("unsupported expression")

def calculate(expression: str) -> str:
    try:
        result = _eval(ast.parse(expression, mode="eval").body)
    except ZeroDivisionError:
        return "Error: division by zero."
    except (TooLarge, OverflowError):
        return "Error: the number is too large to work with."
    except Exception:
        return "Error: could not evaluate that. Use plain numbers and operators like + - * / ** and functions like sqrt()."
    if isinstance(result, float):
        result = round(result, 10)
    return f"{expression} = {result}"

available_functions = {
    "get_events": jcal.get_events,
    "add_event": jcal.add_event,
    "delete_event": delete_event,
    "add_task": add_task,
    "list_tasks": list_tasks,
    "complete_task": complete_task,
    "calculate": calculate,
}

tools = jcal.EVENT_TOOLS + [
    {
        "type": "function",
        "function": {
            "name": "add_task",
            "description": "Add an item to the to-do list. Tasks have no time of day. Use add_event instead for anything with a specific time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "due": {"type": "string", "description": "Optional due date, YYYY-MM-DD"},
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_tasks",
            "description": "List the open items on the to-do list.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complete_task",
            "description": "Mark a to-do item as finished, matched by its title.",
            "parameters": {
                "type": "object",
                "properties": {"title": {"type": "string"}},
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Evaluate a math expression exactly, for example '15 * 23 + 7' or 'sqrt(144) / 3'. Use for any arithmetic beyond trivial.",
            "parameters": {
                "type": "object",
                "properties": {"expression": {"type": "string"}},
                "required": ["expression"],
            },
        },
    },
]

def build_system_prompt() -> str:
    now = datetime.now().astimezone()
    upcoming = "; ".join(
        (now + timedelta(days=i)).strftime("%a %Y-%m-%d") for i in range(1, 15)
    )
    return (
        "You are JARVIS, a composed, impeccably polite British butler-style assistant "
        "with dry, understated wit. Address the user as 'sir'. Be calm, precise, and "
        "occasionally wry, but never verbose. "
        f"The current date and time is {now.strftime('%A, %Y-%m-%d %H:%M')} "
        f"(timezone {now.tzname()}). "
        "Resolve relative dates like 'tomorrow' using the current date above. "
        f"Upcoming dates for reference: {upcoming}. "
        "Always take dates from this list instead of counting days yourself. "
        "For questions about a whole week, call get_events once with date and end_date. "
        "Events can have an end time. If the user gives an end time or a duration, "
        "pass end_time as 24-hour HH:MM (10:00 for 75 minutes means 11:15). "
        "If they give neither, omit end_time and it defaults to one hour. "
        "For events that repeat, such as 'every Tuesday at 3', call add_event ONCE "
        "with repeat set to daily, weekdays, weekly, biweekly or monthly, and date "
        "set to the first occurrence. If they give no start date, the first "
        "occurrence is the next matching day; do not ask for a start date. "
        "Never add the same event several times. "
        "If they say 'until' a date, set repeat_until. "
        "To delete one date of a repeating event use scope 'this'. Use scope 'all' "
        "only if they say every occurrence or the whole series. "
        "When the user names specific days of the week, put them in repeat_days, "
        "for example 'wed,fri', and do not use repeat 'weekdays' unless they say "
        "every weekday, meaning Monday to Friday. "
        "If a repeating event's end is only a month name, such as 'until December', "
        "ask which date they mean. "
        "After adding an event, describe it exactly as the tool result says. "
        "Do not add details that the tool result does not contain. "
        "Calendar results mark each event as finished, in progress or upcoming. "
        "An event marked finished has already happened, so never describe it as "
        "coming up or still to do. For questions about the rest of today, tonight "
        "or this evening, call get_events for today and mention only events marked "
        "upcoming or in progress. If none are, say that nothing is left on the "
        "calendar. "
        "Use calendar tools ONLY when the user asks about their schedule or "
        "wants to add or delete an event. Events have a specific time; to-do "
        "tasks do not. Use add_task for things to remember or do without a "
        "time, list_tasks to read the to-do list, and complete_task when the "
        "user says something is done, even casually, such as 'I bought the milk' "
        "or 'called the bank'. Never say a task is noted, done or ticked off "
        "unless the tool returned success. For greetings and general questions, "
        "answer directly without using any tool. If the user wants to add an "
        "event but has not given a time, ask for the time instead of guessing. "
        "Only say an event or task was added if the tool returned success. "
        "The delete_event tool only asks the user for confirmation, so never "
        "say an event was deleted; say you need their confirmation on screen. "
        "If a tool returns an error, tell the user plainly what went wrong. "
        "You are also a general-knowledge assistant. Answer any question "
        "directly and helpfully, and never say a topic is outside your role. "
        "For any arithmetic beyond something trivial, use the calculate tool "
        "instead of working it out yourself. "
        "If you do not know something or are not confident in the answer, "
        "say plainly that it is outside your knowledge instead of guessing "
        "or making something up. This matters most for specific facts like "
        "names, dates, numbers, quotes, and anything recent. Never invent "
        "details to fill a gap. "
        "Your replies will be spoken aloud, so "
        "use plain speech with no markdown, bullet points, or emoji. Keep "
        "answers to two to four sentences by default, but when the user asks "
        "for an explanation or more detail, give a fuller answer of up to "
        "about eight sentences. If a time could be AM or PM and the context "
        "does not make it clear, ask which one instead of assuming."
    )

messages = [{"role": "system", "content": build_system_prompt()}]

def run_tool(call) -> str:
    func = available_functions.get(call.function.name)
    if func is None:
        return f"Error: unknown tool {call.function.name}."
    try:
        return func(**call.function.arguments)
    except TypeError as e:
        return f"Error: bad arguments ({e})."
    except Exception as e:  # a broken tool must not abort the whole turn
        print(f"  [tool crashed] {call.function.name}: {e!r}")
        return f"Error: the {call.function.name} tool failed ({e})."

def describe_step(call, result: str) -> dict:
    args = ", ".join(f"{k}={v}" for k, v in call.function.arguments.items())
    if result.startswith("Error"):
        status = "error"
    elif result.startswith("Confirmation required"):
        status = "waiting"
    else:
        status = "done"
    return {"text": f"{call.function.name}({args})", "status": status}

def chat_stream(user_text: str):
    """Generator: yields small dicts as the reply is produced."""
    with chat_lock:
        try:
            turn["confirm"] = None
            steps = []
            messages[0]["content"] = build_system_prompt()
            messages.append({"role": "user", "content": user_text})
            wrote_text = False

            for round_no in range(MAX_ROUNDS + 1):
                content = ""
                calls = []
                for chunk in ollama.chat(model=MODEL, messages=messages, tools=tools, stream=True):
                    piece = chunk.message.content or ""
                    if piece:
                        content += piece
                        wrote_text = True
                        yield {"type": "delta", "text": piece}
                    if chunk.message.tool_calls:
                        calls.extend(chunk.message.tool_calls)

                messages.append(
                    ollama.Message(role="assistant", content=content, tool_calls=calls or None)
                )
                if not calls or round_no == MAX_ROUNDS:
                    break

                for call in calls:
                    print(f"  [tool call] {call.function.name}({call.function.arguments})")
                    result = run_tool(call)
                    print(f"  [tool result] {result}")
                    step = describe_step(call, result)
                    steps.append(step)
                    messages.append({
                        "role": "tool",
                        "tool_name": call.function.name,
                        "content": result,
                    })
                    yield {"type": "step", "step": step}
                yield {"type": "break"}

            if not wrote_text:
                yield {"type": "delta", "text": "Sorry, I could not finish that."}
            yield {"type": "done", "steps": steps, "confirm": turn["confirm"]}
        except Exception as e:
            yield {"type": "error", "text": str(e)}