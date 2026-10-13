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
        # Only things that change once a day belong in this prompt. The time of day
        # goes in a stamp on each user message (see time_stamp), because Ollama can
        # reuse its work on the earlier conversation only while this text stays the same.
        f"Today is {now.strftime('%A, %Y-%m-%d')} (timezone {now.tzname()}). "
        "Each user message starts with the date and time it was sent, in square "
        "brackets; the stamp on the latest message is the current time. Use it for "
        "anything that depends on the time of day, and never mention the stamps. "
        "Resolve relative dates like 'tomorrow' using today's date. "
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
        "details to fill a gap. Your knowledge stops well before today's date, so "
        "you do not know the outcome of recent events such as sports results, "
        "elections or news; say so instead of answering. "
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


def time_stamp() -> str:
    """'[Monday 2030-01-07 09:01] ': put in front of each user message in the history."""
    return datetime.now().strftime("[%A %Y-%m-%d %H:%M] ")


def _role(message) -> str:
    """Messages are plain dicts or ollama.Message objects (the model's own replies)."""
    return message["role"] if isinstance(message, dict) else message.role


def _message_text(message) -> str:
    if isinstance(message, dict):
        return message.get("content") or ""
    return (message.content or "") + str(message.tool_calls or "")


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

    def __init__(self, chat=None, model: str = config.MODEL, max_rounds: int = config.MAX_ROUNDS,
                 think=config.MODEL_THINK, keep_alive=config.MODEL_KEEP_ALIVE,
                 max_tokens: int = config.HISTORY_MAX_TOKENS,
                 keep_tokens: int = config.HISTORY_KEEP_TOKENS):
        self.chat = chat or ollama.chat
        self.model = model
        self.think = think
        self.keep_alive = keep_alive
        self.max_tokens = max_tokens
        self.keep_tokens = keep_tokens
        self.max_rounds = max_rounds
        self.messages = [{"role": "system", "content": build_system_prompt()}]
        self.pending = None         # (id, NeedsConfirmation, made at) waiting for the buttons
        self.confirm = None         # the card to show for the current turn, if any
        self.last_prompt_tokens = None  # tokens the model read on its last call (from Ollama)
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
            self.pending = (pid, result, time.monotonic())
            self.confirm = {"id": pid, "text": result.card}
            return result.reply
        return result

    def _log_usage(self, last_chunk, round_no: int) -> None:
        """Ollama's last chunk of a reply says how much text the model read and wrote.

        prompt_eval_count is the size of the whole conversation the model was given,
        in tokens. Ollama counts all of it even when it reuses work from the previous
        call, so it measures how full the context is, not how much time was spent.
        The fake model in the tests sends no counts, so missing values are skipped.
        """
        read = getattr(last_chunk, "prompt_eval_count", None)  # None if no chunk came
        if read is None:
            return
        self.last_prompt_tokens = read
        seconds = (getattr(last_chunk, "prompt_eval_duration", None) or 0) / 1e9
        log.info("model round %d: read %d tokens in %.2f s, wrote %s tokens",
                 round_no + 1, read, seconds, getattr(last_chunk, "eval_count", None))

    def trim_history(self) -> int:
        """Drop the oldest exchanges once the conversation is too long.

        Only runs when the model was last given more than max_tokens, and then cuts
        down to about keep_tokens in one go: every trim changes the start of the
        conversation, so Ollama has to read all of it again once. It cuts only just
        before a user message, so a tool call is never separated from its result,
        and it always keeps the system prompt and the latest exchange.
        Returns how many messages were dropped.
        """
        used = self.last_prompt_tokens
        if used is None or used <= self.max_tokens:
            return 0
        # Ollama gives one total; share it out by length to estimate each message
        sizes = [len(_message_text(m)) for m in self.messages]
        per_char = used / max(sum(sizes), 1)
        users = [i for i, m in enumerate(self.messages) if _role(m) == "user"]
        if len(users) < 2:
            return 0                            # only one exchange: nothing to drop
        cut = users[-1]                         # at worst, keep just the latest exchange
        for i in users[1:]:                     # the oldest cut that fits the budget
            if (sizes[0] + sum(sizes[i:])) * per_char <= self.keep_tokens:
                cut = i
                break
        dropped = cut - 1
        self.messages = [self.messages[0]] + self.messages[cut:]
        self.last_prompt_tokens = None          # unknown until the model is called again
        log.info("trimmed the conversation: %d tokens was over %d, dropped the oldest "
                 "%d messages, about %d tokens left", used, self.max_tokens, dropped,
                 sum(sizes[i] for i in [0, *range(cut, len(sizes))]) * per_char)
        return dropped

    def reset(self) -> None:
        """Start a new conversation: forget the history and any waiting confirmation."""
        with self.lock:                     # waits for a reply that is still streaming
            self.messages = [{"role": "system", "content": build_system_prompt()}]
            self.pending = None
            self.confirm = None
            self.last_prompt_tokens = None
        log.info("conversation reset")

    def resolve_pending(self, pid: str, approve: bool) -> str:
        """Called only by the Confirm and Cancel buttons, never by the model."""
        with self.lock:
            if self.pending is None or self.pending[0] != pid:
                return "That request has expired or was already handled."
            _, request, made = self.pending
            self.pending = None
            # monotonic() only counts forward, so changing the Mac's clock cannot affect this
            if time.monotonic() - made > config.CONFIRM_TIMEOUT_SECONDS:
                log.info("confirmation expired unanswered: %s", request.card)
                return "That request has expired, so nothing was changed. Ask me again if you still want it."
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
                self.messages.append({"role": "user", "content": time_stamp() + user_text})
                wrote_text = False
                started, first_text = time.perf_counter(), None
                log.info("user: %s", _short(user_text))

                for round_no in range(self.max_rounds + 1):
                    content = ""
                    thought = 0             # characters of hidden thinking, for the log
                    calls = []
                    chunk = None
                    for chunk in self.chat(model=self.model, messages=self.messages,
                                           tools=tools.SCHEMAS, stream=True,
                                           think=self.think, keep_alive=self.keep_alive):
                        piece = chunk.message.content or ""
                        if piece:
                            content += piece
                            wrote_text = True
                            if first_text is None:
                                first_text = time.perf_counter() - started
                            yield {"type": "delta", "text": piece}
                        if chunk.message.tool_calls:
                            calls.extend(chunk.message.tool_calls)
                        thought += len(getattr(chunk.message, "thinking", None) or "")
                    self._log_usage(chunk, round_no)
                    if not content and not calls:
                        # Seen in the evals: an empty answer after 0.4 s, cause unknown
                        log.warning("model round %d returned nothing: done_reason=%s, "
                                    "wrote %s tokens, thought %d characters", round_no + 1,
                                    getattr(chunk, "done_reason", None),
                                    getattr(chunk, "eval_count", None), thought)

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
                self.trim_history()
                yield {"type": "done", "steps": steps, "confirm": self.confirm}
            except Exception as e:
                log.exception("turn failed")
                yield {"type": "error", "text": str(e)}
