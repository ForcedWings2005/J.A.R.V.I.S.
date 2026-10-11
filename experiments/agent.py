import sqlite3
import time
import ollama
from datetime import datetime

MODEL = "gemma4:latest"

db = sqlite3.connect("jarvis.db")
db.execute(
    "CREATE TABLE IF NOT EXISTS events ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "title TEXT NOT NULL, date TEXT NOT NULL, time TEXT NOT NULL)"
)
db.commit()

def get_events(date: str) -> str:
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return f"Error: '{date}' is not a valid date. Use YYYY-MM-DD."
    rows = db.execute(
        "SELECT time, title FROM events WHERE date = ? ORDER BY time", (date,)
    ).fetchall()
    if not rows:
        return f"No events on {date}."
    lines = [f"{t} {title}" for t, title in rows]
    return f"Events on {date}: " + "; ".join(lines)

def add_event(title: str, date: str, start_time: str) -> str:
    try:
        when = datetime.strptime(f"{date} {start_time}", "%Y-%m-%d %H:%M")
    except ValueError:
        return "Error: use date YYYY-MM-DD and start_time HH:MM (24-hour)."
    if when < datetime.now():
        return "Error: that time is in the past."
    clean_time = when.strftime("%H:%M")
    clash = db.execute(
        "SELECT title FROM events WHERE date = ? AND time = ?", (date, clean_time)
    ).fetchone()
    if clash:
        return f"Error: conflicts with '{clash[0]}' at {clean_time} on {date}."
    db.execute(
        "INSERT INTO events (title, date, time) VALUES (?, ?, ?)",
        (title, date, clean_time),
    )
    db.commit()
    return f"Added '{title}' on {date} at {clean_time}."

available_functions = {"get_events": get_events, "add_event": add_event}

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_events",
            "description": "List calendar events for a date (YYYY-MM-DD)",
            "parameters": {
                "type": "object",
                "properties": {"date": {"type": "string"}},
                "required": ["date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_event",
            "description": "Add a calendar event. Only call when the user has given a title, a date and a start time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "start_time": {"type": "string", "description": "HH:MM, 24-hour"},
                },
                "required": ["title", "date", "start_time"],
            },
        },
    },
]

def build_system_prompt() -> str:
    now = datetime.now().astimezone()
    return (
        "You are JARVIS, a concise, helpful personal assistant. "
        f"The current date and time is {now.strftime('%A, %Y-%m-%d %H:%M')} "
        f"(timezone {now.tzname()}). "
        "Resolve relative dates like 'tomorrow' using the current date above. "
        "Use calendar tools ONLY when the user asks about their schedule or "
        "wants to add an event. For greetings and general questions, answer "
        "directly without using any tool. If the user wants to add an event "
        "but has not given a time, ask for the time instead of guessing. "
        "Only say an event was added if the add_event tool returned success. "
        "If a tool returns an error, tell the user plainly what went wrong."
        "If a tool returns an error, tell the user plainly what went wrong."
        " Your replies will be spoken aloud, so keep them to one to three "
        "short sentences, in plain speech with no markdown, bullet points, "
        "or emoji."
        " If a time could be AM or PM and the context does not make it clear, "
        "ask which one instead of assuming."
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

def chat(user_text: str) -> str:
    messages.append({"role": "user", "content": user_text})
    resp = ollama.chat(model=MODEL, messages=messages, tools=tools)
    messages.append(resp.message)

    if resp.message.tool_calls:
        for call in resp.message.tool_calls:
            print(f"  [tool call] {call.function.name}({call.function.arguments})")
            result = run_tool(call)
            print(f"  [tool result] {result}")
            messages.append({
                "role": "tool",
                "tool_name": call.function.name,
                "content": result,
            })
        final = ollama.chat(model=MODEL, messages=messages)
        messages.append(final.message)
        return final.message.content

    return resp.message.content

while True:
    user_text = input("You: ")
    if user_text.strip().lower() in ("quit", "exit"):
        break
    start = time.perf_counter()
    reply = chat(user_text)
    elapsed = time.perf_counter() - start
    print("JARVIS:", reply)
    print(f"  [{elapsed:.1f}s]")