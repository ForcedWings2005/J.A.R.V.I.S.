"""The assistant: talks to the model, runs the tools it asks for, keeps the conversation.

The tools themselves live in jcal.py (calendar), tasks.py (to-do list) and calc.py
(calculator), registered with tools.py. Importing them below is what registers them.
"""
import logging
import threading
import time
import uuid
from datetime import datetime, timedelta

import ollama

import config
import tools
# Importing these registers their tools. The order is the order the model sees them.
import jcal  # noqa: F401, E402
import tasks  # noqa: F401, E402
import calc  # noqa: F401, E402

log = logging.getLogger("jarvis.brain")


def _short(text, limit: int = 300) -> str:
    text = str(text).replace("\n", " ")
    return text if len(text) <= limit else text[:limit] + "..."


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
        "The list is only a lookup aid; the calendar itself has no end. For a date "
        "beyond the list, such as 'March 3rd', use the next such date that is not "
        "in the past and call the tool as usual; never tell the user a date is "
        "outside your calendar or range. "
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
        "use plain speech with no markdown, bullet points, or emoji. "
        "Always write numbers as digits, never as words, and copy them exactly as "
        "a tool result gives them, for example 7006652 or 38.4444; the speech "
        "system reads digits aloud correctly. Keep "
        "answers to two to four sentences by default, but when the user asks "
        "for an explanation or more detail, give a fuller answer of up to "
        "about eight sentences. If a time could be AM or PM and the context "
        "does not make it clear, ask which one instead of assuming."
    )


def describe_step(call, result: str) -> dict:
    """One line for the activity ticker under the transcript."""
    args = ", ".join(f"{k}={v}" for k, v in call.function.arguments.items())
    if result.startswith("Error"):
        status = "error"
    elif result.startswith("Confirmation required"):
        status = "waiting"
    else:
        status = "done"
    return {"text": f"{call.function.name}({args})", "status": status}


class Assistant:
    """One conversation with JARVIS: its history, a pending confirmation, and the model.

    `chat` is the function that talks to the model (ollama.chat). Tests pass a fake
    one that plays back scripted replies, so no model is needed.
    """

    def __init__(self, chat=None, model: str = config.MODEL, max_rounds: int = config.MAX_ROUNDS):
        self.chat = chat or ollama.chat
        self.model = model
        self.max_rounds = max_rounds
        self.messages = [{"role": "system", "content": build_system_prompt()}]
        self.pending = None         # (id, NeedsConfirmation) waiting for the buttons
        self.confirm = None         # the card to show for the current turn, if any
        self.lock = threading.Lock()

    def run_tool(self, call) -> str:
        func = tools.FUNCTIONS.get(call.function.name)
        if func is None:
            return f"Error: unknown tool {call.function.name}."
        try:
            result = func(**call.function.arguments)
        except TypeError as e:
            return f"Error: bad arguments ({e})."
        except Exception as e:  # a broken tool must not abort the whole turn
            log.exception("tool %s crashed", call.function.name)
            return f"Error: the {call.function.name} tool failed ({e})."
        if isinstance(result, tools.NeedsConfirmation):
            # Only one request can wait at a time; a new one replaces it
            pid = uuid.uuid4().hex[:8]
            self.pending = (pid, result)
            self.confirm = {"id": pid, "text": result.card}
            return result.reply
        return result

    def resolve_pending(self, pid: str, approve: bool) -> str:
        """Called only by the Confirm and Cancel buttons, never by the model."""
        with self.lock:
            if self.pending is None or self.pending[0] != pid:
                return "That request has expired or was already handled."
            _, request = self.pending
            self.pending = None
            text = request.apply() if approve else "Okay, I left it alone."
            log.info("confirmation %s: %s -> %s", "approved" if approve else "cancelled",
                     request.card, text)
            self.messages.append({"role": "assistant", "content": text})
            return text

    def chat_stream(self, user_text: str):
        """Generator: yields small dicts as the reply is produced.

        delta (a piece of text), step (a tool ran), break (a tool round ended),
        done (steps and any confirmation card), error.
        """
        with self.lock:
            try:
                self.confirm = None
                steps = []
                self.messages[0]["content"] = build_system_prompt()
                self.messages.append({"role": "user", "content": user_text})
                wrote_text = False
                started, first_text = time.perf_counter(), None
                log.info("user: %s", _short(user_text))

                for round_no in range(self.max_rounds + 1):
                    content = ""
                    calls = []
                    for chunk in self.chat(model=self.model, messages=self.messages,
                                           tools=tools.SCHEMAS, stream=True):
                        piece = chunk.message.content or ""
                        if piece:
                            content += piece
                            wrote_text = True
                            if first_text is None:
                                first_text = time.perf_counter() - started
                            yield {"type": "delta", "text": piece}
                        if chunk.message.tool_calls:
                            calls.extend(chunk.message.tool_calls)

                    self.messages.append(
                        ollama.Message(role="assistant", content=content, tool_calls=calls or None)
                    )
                    if not calls or round_no == self.max_rounds:
                        break

                    for call in calls:
                        t0 = time.perf_counter()
                        result = self.run_tool(call)
                        log.info("tool %s(%s) -> %s [%.0f ms]", call.function.name,
                                 _short(call.function.arguments), _short(result),
                                 (time.perf_counter() - t0) * 1000)
                        step = describe_step(call, result)
                        steps.append(step)
                        self.messages.append({
                            "role": "tool",
                            "tool_name": call.function.name,
                            "content": result,
                        })
                        yield {"type": "step", "step": step}
                    yield {"type": "break"}

                if not wrote_text:
                    log.warning("no reply text after %d rounds", round_no + 1)
                    yield {"type": "delta", "text": "Sorry, I could not finish that."}
                log.info("reply: %s [%d rounds, %d tools, first text %s, total %.1f s]",
                         _short(content), round_no + 1, len(steps),
                         f"{first_text:.1f} s" if first_text is not None else "none",
                         time.perf_counter() - started)
                yield {"type": "done", "steps": steps, "confirm": self.confirm}
            except Exception as e:
                log.exception("turn failed")
                yield {"type": "error", "text": str(e)}
