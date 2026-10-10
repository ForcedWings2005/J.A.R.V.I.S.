import time
import ollama
from datetime import datetime, timedelta

MODELS = ["mistral:latest", "gemma4:latest", "qwen3.5:latest"]
RUNS = 3

tools = [{
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
}]

def build_system_prompt() -> str:
    now = datetime.now().astimezone()
    return (
        "You are JARVIS, a concise, helpful personal assistant. "
        f"The current date and time is {now.strftime('%A, %Y-%m-%d %H:%M')} "
        f"(timezone {now.tzname()}). "
        "Resolve relative dates like 'tomorrow' using the current date above. "
        "Use the get_events tool ONLY when the user asks about their calendar "
        "or schedule. For greetings and general questions, answer directly "
        "without using any tool."
    )

today = datetime.now().date()
tomorrow = (today + timedelta(days=1)).isoformat()
day_after = (today + timedelta(days=2)).isoformat()
days_to_friday = (4 - today.weekday()) % 7 or 7
friday1 = (today + timedelta(days=days_to_friday)).isoformat()
friday2 = (today + timedelta(days=days_to_friday + 7)).isoformat()

TURNS = [
    ("Hello", None),
    ("What's on my calendar tomorrow?", {tomorrow}),
    ("What about the day after?", {day_after}),
    ("What's on my calendar next Friday?", {friday1, friday2}),
    ("What's the capital of France?", None),
]

def run_session(model: str) -> int:
    messages = [{"role": "system", "content": build_system_prompt()}]
    passed = 0
    try:
        for user_text, expected in TURNS:
            messages.append({"role": "user", "content": user_text})
            resp = ollama.chat(model=model, messages=messages, tools=tools)
            messages.append(resp.message)
            calls = resp.message.tool_calls or []
            content = resp.message.content or ""

            if expected is None:
                ok = len(calls) == 0
            else:
                ok = False
                if len(calls) == 1:
                    date = calls[0].function.arguments.get("date")
                    ok = calls[0].function.name == "get_events" and date in expected
            if "[TOOL_CALLS]" in content:
                ok = False

            if ok:
                passed += 1
            else:
                print(f"  FAIL [{model}] '{user_text}' calls={calls} text={content[:60]!r}")

            if calls:
                for call in calls:
                    messages.append({
                        "role": "tool",
                        "tool_name": call.function.name,
                        "content": "Events: 10:00 Standup, 14:00 Dentist",
                    })
                final = ollama.chat(model=model, messages=messages)
                messages.append(final.message)
    except ollama.ResponseError as e:
        print(f"  ERROR [{model}]: {e}")
        return 0
    return passed

for model in MODELS:
    start = time.perf_counter()
    scores = [run_session(model) for _ in range(RUNS)]
    avg_seconds = (time.perf_counter() - start) / RUNS
    print(f"{model}: scores {scores} out of {len(TURNS)}, avg {avg_seconds:.1f}s per session\n")