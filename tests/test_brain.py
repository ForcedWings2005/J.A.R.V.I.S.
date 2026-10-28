"""Tests for the assistant loop in brain.py, with a fake model.

The fake plays back scripted rounds: each round is some text and/or tool calls,
streamed in small chunks the way Ollama sends them.
"""
from datetime import datetime

import ollama
import pytest

import brain
import config
import jcal
import notes
import tasks
import tools
from fakes import FakeModel, call, say, use


def run(assistant, message):
    events = list(assistant.chat_stream(message))
    reply = "".join(e["text"] for e in events if e["type"] == "delta")
    return events, reply


# --- plain conversation ------------------------------------------------------

def test_plain_reply_is_streamed_and_kept_in_the_history():
    a = brain.Assistant(chat=FakeModel(say("Good morning, sir.")))
    events, reply = run(a, "Good morning")
    assert reply == "Good morning, sir."
    assert sum(e["type"] == "delta" for e in events) > 1          # arrived in pieces
    assert events[-1] == {"type": "done", "steps": [], "confirm": None}
    assert a.messages[-2]["role"] == "user"
    assert a.messages[-2]["content"].endswith("] Good morning")
    assert a.messages[-1].content == "Good morning, sir."


def test_the_conversation_continues_across_turns():
    model = FakeModel(say("Hello, sir."), say("You said hello."))
    a = brain.Assistant(chat=model)
    run(a, "Hello")
    run(a, "What did I say?")
    contents = [getattr(m, "content", None) or m.get("content") for m in model.seen[1]]
    assert any(c and c.endswith("] Hello") for c in contents) and "Hello, sir." in contents


def test_system_prompt_is_rebuilt_every_turn(monkeypatch):
    model = FakeModel(say("One."), say("Two."))
    a = brain.Assistant(chat=model)
    monkeypatch.setattr(brain, "build_system_prompt", lambda: "PROMPT A")
    run(a, "first")
    monkeypatch.setattr(brain, "build_system_prompt", lambda: "PROMPT B")
    run(a, "second")
    assert model.seen[0][0]["content"] == "PROMPT A"
    assert model.seen[1][0]["content"] == "PROMPT B"


@pytest.fixture
def brain_clock(monkeypatch):
    """Freeze datetime.now() inside brain.py; tests move it with brain_clock[0] = ..."""
    now = [datetime(2030, 1, 7, 9, 0)]

    class FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(*now[0].timetuple()[:6])

    monkeypatch.setattr(brain, "datetime", FakeDateTime)
    return now


def test_each_user_message_is_stamped_with_the_time_it_was_sent(brain_clock):
    a = brain.Assistant(chat=FakeModel(say("Morning."), say("Evening.")))
    run(a, "Good morning")
    brain_clock[0] = datetime(2030, 1, 7, 19, 30)
    run(a, "Good evening")
    users = [m["content"] for m in a.messages if isinstance(m, dict) and m["role"] == "user"]
    assert users == ["[Monday 2030-01-07 09:00] Good morning",
                     "[Monday 2030-01-07 19:30] Good evening"]


def test_the_stamp_names_the_space_except_home(brain_clock):
    a = brain.Assistant(chat=FakeModel(say("A."), say("B.")))
    list(a.chat_stream("In work", space="work"))
    list(a.chat_stream("At home"))
    users = [m["content"] for m in a.messages if isinstance(m, dict) and m["role"] == "user"]
    assert users == ["[Monday 2030-01-07 09:00 · Work] In work",
                     "[Monday 2030-01-07 09:00] At home"]


def test_the_system_prompt_does_not_change_with_the_space(brain_clock):
    """The space is in the stamp only, so Ollama can still reuse its work (section 27)."""
    model = FakeModel(say("A."), say("B."))
    a = brain.Assistant(chat=model)
    list(a.chat_stream("x", space="work"))
    list(a.chat_stream("y"))
    assert model.seen[0][0]["content"] == model.seen[1][0]["content"]


def test_system_prompt_stays_the_same_all_day(brain_clock):
    """So Ollama can reuse its work on the earlier conversation (CHANGELOG section 27)."""
    morning = brain.build_system_prompt()
    brain_clock[0] = datetime(2030, 1, 7, 23, 59)
    assert brain.build_system_prompt() == morning
    assert "Today is Monday, 2030-01-07" in morning
    brain_clock[0] = datetime(2030, 1, 8, 0, 0)
    assert "Today is Tuesday, 2030-01-08" in brain.build_system_prompt()


def test_no_text_at_all_gets_an_apology():
    a = brain.Assistant(chat=FakeModel(say(""), say("")))          # empty, and empty again
    _, reply = run(a, "Hm")
    assert reply == "Sorry, I could not finish that."


def test_a_model_error_is_reported_not_raised():
    def broken(**kwargs):
        raise ConnectionError("Ollama is not running")
        yield  # pragma: no cover  (makes this a generator)

    a = brain.Assistant(chat=broken)
    events, _ = run(a, "Hello")
    assert events[-1] == {"type": "error", "text": "Ollama is not running"}


# --- tool rounds -------------------------------------------------------------

def test_tool_round_runs_the_tool_and_feeds_back_the_result():
    model = FakeModel(use(call("add_task", title="Buy milk")), say("Added, sir."))
    a = brain.Assistant(chat=model)
    events, reply = run(a, "Add buy milk to my list")
    assert reply == "Added, sir."
    assert [t["title"] for t in tasks.tasks_list()] == ["Buy milk"]
    steps = [e["step"] for e in events if e["type"] == "step"]
    assert steps == [{"text": "Added the task 'Buy milk'", "status": "done"}]
    assert [e["type"] for e in events].count("break") == 1
    tool_msg = model.seen[1][-1]
    assert tool_msg == {"role": "tool", "tool_name": "add_task", "content": "Added task 'Buy milk'."}


def test_several_tools_in_one_round():
    model = FakeModel(use(call("add_task", title="A"), call("add_task", title="B")), say("Both."))
    events, _ = run(brain.Assistant(chat=model), "Add A and B")
    assert sum(e["type"] == "step" for e in events) == 2
    assert len(tasks.tasks_list()) == 2


def test_opening_a_space_streams_a_space_event_after_its_step():
    model = FakeModel(use(call("open_space", name="work")), say("Work it is, sir."))
    events, reply = run(brain.Assistant(chat=model), "Let's get some work done")
    types = [e["type"] for e in events]
    assert types.index("space") == types.index("step") + 1
    assert next(e for e in events if e["type"] == "space") == {"type": "space", "name": "work"}
    assert next(e["step"] for e in events if e["type"] == "step") == \
        {"text": "Showed the Work space", "status": "done"}
    assert model.seen[1][-1]["content"] == "Showing the Work space."
    assert reply == "Work it is, sir."


def test_an_unknown_space_streams_no_space_event():
    model = FakeModel(use(call("open_space", name="gym")), say("There is no gym, sir."))
    events, _ = run(brain.Assistant(chat=model), "Open the gym")
    assert "space" not in [e["type"] for e in events]
    assert model.seen[1][-1]["content"].endswith("Spaces: home, work.")   # no NO_CARD note


def test_a_space_is_shown_only_on_its_own_turn():
    model = FakeModel(use(call("open_space", name="work")), say("Done."), say("Hello."))
    a = brain.Assistant(chat=model)
    run(a, "Work time")
    events, _ = run(a, "Hello")
    assert "space" not in [e["type"] for e in events]


def test_tool_errors_are_marked_as_errors():
    model = FakeModel(use(call("complete_task", title="nothing")), say("No such task."))
    events, _ = run(brain.Assistant(chat=model), "Done with nothing")
    step = next(e["step"] for e in events if e["type"] == "step")
    assert step["status"] == "error"


# --- the activity line, in plain words (CHANGELOG section 40) ---------------------

@pytest.mark.parametrize("name, args, result, text, status", [
    ("get_events", {"date": "2030-01-08"}, "Events on ...", "Checked the calendar for Tue 8 Jan", "done"),
    ("get_events", {"date": "2030-01-07", "end_date": "2030-01-13"}, "Events ...",
     "Checked the calendar, Mon 7 Jan to Sun 13 Jan", "done"),
    ("add_event", {"title": "Gym", "date": "2030-01-08", "start_time": "18:00"}, "Added 'Gym' ...",
     "Added 'Gym' to the calendar", "done"),
    ("delete_event", {"title": "dentist", "date": "2030-01-08"}, "Confirmation required. ...",
     "Delete 'dentist': waiting for your Confirm", "waiting"),
    ("update_event", {"title": "dentist", "new_start_time": "16:00"}, "Confirmation required. ...",
     "Change 'dentist': waiting for your Confirm", "waiting"),
    ("list_tasks", {}, "Open tasks: ...", "Read the to-do list", "done"),
    ("complete_task", {"title": "milk"}, "Marked 'Buy milk' as done.", "Ticked off 'milk'", "done"),
    ("calculate", {"expression": "0.15 * 240"}, "36", "Calculated 0.15 * 240", "done"),
    ("recall", {"about": "food"}, "Saved notes ...", "Looked through your notes", "done"),
])
def test_steps_are_described_in_plain_words(name, args, result, text, status):
    assert brain.describe_step(call(name, **args), result) == {"text": text, "status": status}


def test_a_failed_step_says_what_went_wrong_briefly():
    step = brain.describe_step(call("delete_event", title="dentist"),
                               "Error: give the date of the occurrence to delete, or use scope "
                               "'all' to delete a whole repeating series.")
    assert step["status"] == "error"
    assert step["text"].startswith("Delete 'dentist': give the date of the occurrence")
    assert len(step["text"]) <= 90


# A call the code refuses and the model then fixes in the same reply showed a red "!" in
# the ticker, although it worked in the end (CHANGELOG section 47). It is now "corrected".

def test_a_refused_call_the_model_then_fixes_is_shown_as_corrected():
    jcal.add_event("Meeting", "2030-01-10", "09:00", repeat="biweekly", repeat_days="thu")
    model = FakeModel(use(call("delete_event", title="meeting")),
                      use(call("delete_event", title="Meeting", scope="all")),
                      say("Please confirm on screen, sir."))
    events, _ = run(brain.Assistant(chat=model), "Delete every meeting")
    assert [s["status"] for s in events[-1]["steps"]] == ["corrected", "waiting"]


def test_a_refused_call_that_is_not_fixed_stays_an_error():
    jcal.add_event("Meeting", "2030-01-10", "09:00", repeat="biweekly", repeat_days="thu")
    model = FakeModel(use(call("delete_event", title="meeting")),
                      say("One date, or the whole series, sir?"))
    events, _ = run(brain.Assistant(chat=model), "Delete the meeting")
    assert [s["status"] for s in events[-1]["steps"]] == ["error"]


def test_a_success_for_another_event_does_not_hide_an_error():
    jcal.add_event("Dentist", "2030-01-08", "15:00")
    model = FakeModel(use(call("delete_event", title="meeting")),
                      use(call("delete_event", title="dentist", date="2030-01-08")),
                      say("Please confirm on screen, sir."))
    events, _ = run(brain.Assistant(chat=model), "Cancel the meeting and the dentist")
    assert [s["status"] for s in events[-1]["steps"]] == ["error", "waiting"]


def test_note_steps_never_show_the_note_itself():
    for name, args in (("remember", {"text": "Likes xyzzy"}), ("forget", {"about": "xyzzy"}),
                       ("recall", {"about": "xyzzy"})):
        assert "xyzzy" not in brain.describe_step(call(name, **args), "Confirmation required.")["text"]


def test_an_unknown_tool_is_still_described():
    assert brain.describe_step(call("teleport", place="Mars"), "ok")["text"] == "teleport(place=Mars)"


def test_rounds_are_capped():
    """A model that keeps calling tools is stopped after max_rounds tool rounds."""
    loop = [use(call("list_tasks")) for _ in range(10)]
    model = FakeModel(*loop)
    a = brain.Assistant(chat=model, max_rounds=2)
    events, reply = run(a, "Loop forever")
    assert len(model.seen) == 3                 # 2 tool rounds, then one last answer
    assert sum(e["type"] == "step" for e in events) == 2
    assert reply == "Sorry, I could not finish that."


# --- run_tool ----------------------------------------------------------------

def test_unknown_tool():
    assert brain.Assistant(chat=FakeModel()).run_tool(call("launch_rockets")) == \
        "Error: unknown tool launch_rockets."


def test_bad_arguments():
    result = brain.Assistant(chat=FakeModel()).run_tool(call("add_task", colour="red"))
    assert result.startswith("Error: bad arguments")


def test_a_crashing_tool_becomes_an_error_result(monkeypatch):
    def boom():
        raise RuntimeError("disk on fire")

    monkeypatch.setitem(tools.FUNCTIONS, "boom", boom)
    result = brain.Assistant(chat=FakeModel()).run_tool(call("boom"))
    assert result == "Error: the boom tool failed (disk on fire)."


# A tool that only asks for confirmation can fail before any card appears. JARVIS then
# still said "you'll need to confirm on screen" (CHANGELOG sections 40 and 44), so its
# errors now say that no card was shown.

@pytest.mark.parametrize("name, args", [
    ("delete_event", {"title": "dentist"}),                        # no date given
    ("update_event", {"title": "dentist", "date": "2030-01-08", "new_start_time": "16:00"}),
    ("remember", {"text": ""}),
    ("forget", {"about": "sushi"}),
])
def test_an_error_from_a_tool_that_asks_first_says_no_card_was_shown(name, args):
    assert name in tools.ASKS_FIRST
    a = brain.Assistant(chat=FakeModel())
    result = a.run_tool(call(name, **args))
    assert result.startswith("Error:") and result.endswith(brain.NO_CARD)
    assert a.pending is None and a.confirm is None


def test_a_crash_in_a_tool_that_asks_first_says_no_card_was_shown(monkeypatch):
    def boom(title, date="", scope="this"):
        raise RuntimeError("disk on fire")

    monkeypatch.setitem(tools.FUNCTIONS, "delete_event", boom)
    result = brain.Assistant(chat=FakeModel()).run_tool(call("delete_event", title="x"))
    assert result == "Error: the delete_event tool failed (disk on fire)." + brain.NO_CARD


def test_other_tools_errors_are_unchanged():
    result = brain.Assistant(chat=FakeModel()).run_tool(call("complete_task", title="unicorn"))
    assert result == "Error: no open task matching 'unicorn'."


def test_a_request_that_shows_a_card_gets_no_note():
    jcal.add_event("Dentist", "2030-01-08", "15:00")
    result = brain.Assistant(chat=FakeModel()).run_tool(
        call("delete_event", title="dentist", date="2030-01-08"))
    assert result.startswith("Confirmation required") and brain.NO_CARD not in result


# --- delete confirmation -----------------------------------------------------

def _delete_turn(a_model_reply="Please confirm on screen, sir."):
    jcal.add_event("Dentist", "2030-01-08", "15:00")
    model = FakeModel(use(call("delete_event", title="dentist", date="2030-01-08")),
                      say(a_model_reply))
    a = brain.Assistant(chat=model)
    events, _ = run(a, "Cancel the dentist tomorrow")
    return a, events


def test_delete_only_asks_for_confirmation():
    a, events = _delete_turn()
    done = events[-1]
    assert done["confirm"]["text"] == "Delete 'Dentist' on 2030-01-08 at 15:00?"
    step = next(e["step"] for e in events if e["type"] == "step")
    assert step["status"] == "waiting"
    assert "Dentist" in jcal.get_events("2030-01-08")           # nothing deleted yet


def test_confirm_deletes_and_is_remembered_in_the_conversation():
    a, events = _delete_turn()
    pid = events[-1]["confirm"]["id"]
    assert a.resolve_pending(pid, True) == "Done. The event has been deleted."
    assert jcal.get_events("2030-01-08").startswith("No events")
    assert a.messages[-1] == {"role": "assistant", "content": "Done. The event has been deleted."}


def test_cancel_leaves_the_event():
    a, events = _delete_turn()
    assert a.resolve_pending(events[-1]["confirm"]["id"], False) == "Okay, I left it alone."
    assert "Dentist" in jcal.get_events("2030-01-08")


@pytest.mark.parametrize("pid", ["wrong-id", None])
def test_a_wrong_or_used_id_does_nothing(pid):
    a, events = _delete_turn()
    real = events[-1]["confirm"]["id"]
    if pid is None:                             # use it once, then try again
        a.resolve_pending(real, False)
        pid = real
    assert a.resolve_pending(pid, True) == "That request has expired or was already handled."
    assert "Dentist" in jcal.get_events("2030-01-08")


def test_the_card_is_only_reported_on_its_own_turn():
    a, _ = _delete_turn()
    a.chat = FakeModel(say("Anything else, sir?"))
    events, _ = run(a, "Thanks")
    assert events[-1]["confirm"] is None


# --- logging -----------------------------------------------------------------

def test_turns_and_tool_calls_are_logged(caplog):
    caplog.set_level("INFO", logger="jarvis")
    model = FakeModel(use(call("add_task", title="Buy milk")), say("Added, sir."))
    run(brain.Assistant(chat=model), "Add buy milk")
    assert "user: Add buy milk" in caplog.text
    assert "tool add_task({'title': 'Buy milk'}) -> Added task 'Buy milk'." in caplog.text
    assert "reply: Added, sir. [2 rounds, 1 tools, first text" in caplog.text


def test_note_text_never_reaches_the_log_when_saving(caplog):
    """SECURITY.md: the log records a note's length, never its words, for tool calls and cards."""
    caplog.set_level("INFO", logger="jarvis")
    model = FakeModel(use(call("remember", text="Favourite food is xyzzy")),
                      say("Please confirm on screen, sir."))
    a = brain.Assistant(chat=model)
    events, _ = run(a, "Note that down")
    a.resolve_pending(events[-1]["confirm"]["id"], True)
    assert notes.recall("xyzzy").endswith("Favourite food is xyzzy")     # it was saved
    assert "tool remember(23 characters)" in caplog.text
    assert "confirmation approved" in caplog.text
    assert "xyzzy" not in caplog.text


def test_note_text_never_reaches_the_log_when_recalling_or_forgetting(caplog):
    notes.remember("Prefers window seats").apply()
    caplog.set_level("INFO", logger="jarvis")
    model = FakeModel(use(call("recall", about="seats")), say("Noted, sir."),
                      use(call("forget", about="seats")), say("Please confirm, sir."))
    a = brain.Assistant(chat=model)
    run(a, "What do I like?")
    events, _ = run(a, "Drop that one")
    a.resolve_pending(events[-1]["confirm"]["id"], True)
    assert notes.recall() == "No saved notes yet."                       # it was forgotten
    assert "tool recall(5 characters)" in caplog.text
    assert "window" not in caplog.text and "seats" not in caplog.text


def test_a_crashing_tool_is_logged_with_its_traceback(caplog, monkeypatch):
    def boom():
        raise RuntimeError("disk on fire")

    monkeypatch.setitem(tools.FUNCTIONS, "boom", boom)
    brain.Assistant(chat=FakeModel()).run_tool(call("boom"))
    assert "tool boom crashed" in caplog.text and "RuntimeError: disk on fire" in caplog.text


def test_token_counts_from_ollama_are_logged_and_kept(caplog):
    def chat(**kwargs):
        yield ollama.ChatResponse(message=ollama.Message(role="assistant", content="Hello."),
                                  done=True, prompt_eval_count=2056,
                                  prompt_eval_duration=1_500_000_000, eval_count=12)

    caplog.set_level("INFO", logger="jarvis")
    a = brain.Assistant(chat=chat)
    run(a, "Hi")
    assert a.last_prompt_tokens == 2056
    assert "model round 1: read 2056 tokens in 1.50 s, wrote 12 tokens" in caplog.text


def test_think_and_keep_alive_settings_reach_the_model():
    model = FakeModel(say("Hello."))
    run(brain.Assistant(chat=model, think=False, keep_alive="1h"), "Hi")
    assert model.options["think"] is False and model.options["keep_alive"] == "1h"


# One eval reply looped for 39 minutes and 121,120 tokens, and nothing stopped it
# (CHANGELOG section 47). Every request now carries a cap on what one round may write.

def test_every_request_caps_the_length_of_the_reply():
    model = FakeModel(say("Hello."))
    run(brain.Assistant(chat=model), "Hi")
    assert model.options["options"] == {"num_predict": config.MODEL_MAX_TOKENS}


def test_reaching_the_cap_is_logged(caplog):
    def chat(**kwargs):
        yield ollama.ChatResponse(message=ollama.Message(role="assistant", content="And so on"),
                                  done=True, done_reason="length", eval_count=4096)

    run(brain.Assistant(chat=chat), "Hi")
    assert "model round 1 stopped at the 4096-token limit" in caplog.text


def test_an_empty_model_round_is_logged(caplog):
    a = brain.Assistant(chat=FakeModel(say(""), say("")))
    _, reply = run(a, "Hm")
    assert reply == "Sorry, I could not finish that."
    assert "model round 1 returned nothing" in caplog.text
    assert "retrying once" in caplog.text and "giving up" in caplog.text


def test_an_empty_answer_is_retried_once(caplog):
    caplog.set_level("INFO", logger="jarvis")
    model = FakeModel(say(""), say("Good evening, sir."))
    a = brain.Assistant(chat=model)
    events, reply = run(a, "Good evening")
    assert reply == "Good evening, sir."
    assert len(model.seen) == 2
    assert model.seen[0] == model.seen[1]                       # the same request again
    assert "the retry worked" in caplog.text
    assert [brain._role(m) for m in a.messages[-2:]] == ["user", "assistant"]   # no empty reply kept


def test_an_empty_round_after_a_tool_is_retried_too():
    model = FakeModel(use(call("list_tasks")), say(""), say("No tasks, sir."))
    _, reply = run(brain.Assistant(chat=model), "Any tasks?")
    assert reply == "No tasks, sir."


# --- trimming a long conversation --------------------------------------------

def counting_model(tokens_per_message):
    """A fake model that reports a token count growing with the conversation."""
    def chat(model, messages, tools, stream, **options):
        yield ollama.ChatResponse(message=ollama.Message(role="assistant", content="Noted, sir."),
                                  done=True, prompt_eval_count=tokens_per_message * len(messages))
    return chat


def user_texts(a):
    return [m["content"].split("] ", 1)[1] for m in a.messages
            if isinstance(m, dict) and m["role"] == "user"]


def test_a_short_conversation_is_never_trimmed():
    a = brain.Assistant(chat=counting_model(100))
    for i in range(5):
        run(a, f"message {i}")
    assert user_texts(a) == [f"message {i}" for i in range(5)]


def test_a_long_conversation_is_trimmed_oldest_first_in_one_go():
    # 100 tokens per message; trim above 2000 (20 messages) down to about 1000
    a = brain.Assistant(chat=counting_model(100), max_tokens=2000, keep_tokens=1000)
    sizes = []
    for i in range(30):
        run(a, f"message {i:02d}")
        sizes.append(len(a.messages))
    assert a.messages[0]["role"] == "system"
    assert user_texts(a)[-1] == "message 29"               # the latest is always kept
    assert user_texts(a) == sorted(user_texts(a))          # oldest went first, order kept
    assert max(sizes) <= 21                                # never far over the limit
    drops = sum(1 for before, after in zip(sizes, sizes[1:], strict=False) if after < before)
    assert 1 <= drops <= 3                                 # rarely, a big cut each time


def test_trimming_never_separates_a_tool_call_from_its_result():
    a = brain.Assistant(chat=FakeModel(), max_tokens=10, keep_tokens=5)
    tool_call = ollama.Message(role="assistant", content="", tool_calls=[call("list_tasks")])
    a.messages = [
        {"role": "system", "content": "S"},
        {"role": "user", "content": "[t] first " + "x" * 400},
        tool_call,
        {"role": "tool", "tool_name": "list_tasks", "content": "No open tasks." + "y" * 400},
        ollama.Message(role="assistant", content="Nothing to do."),
        {"role": "user", "content": "[t] second"},
        tool_call,
        {"role": "tool", "tool_name": "list_tasks", "content": "No open tasks."},
        ollama.Message(role="assistant", content="Still nothing."),
    ]
    a.last_prompt_tokens = 500
    assert a.trim_history() == 4
    assert [brain._role(m) for m in a.messages] == ["system", "user", "assistant", "tool", "assistant"]
    assert a.messages[1]["content"] == "[t] second"


def test_trimming_is_logged(caplog):
    caplog.set_level("INFO", logger="jarvis")
    a = brain.Assistant(chat=counting_model(100), max_tokens=500, keep_tokens=300)
    for i in range(6):
        run(a, f"message {i}")
    assert "trimmed the conversation" in caplog.text


# --- expiring confirmations and starting over --------------------------------

def test_an_old_confirmation_can_no_longer_be_used():
    a, events = _delete_turn()
    pid, request, made = a.pending
    a.pending = (pid, request, made - config.CONFIRM_TIMEOUT_SECONDS - 1)
    assert a.resolve_pending(pid, True).startswith("That request has expired, so nothing was changed")
    assert "Dentist" in jcal.get_events("2030-01-08")
    assert a.resolve_pending(pid, True) == "That request has expired or was already handled."


def test_an_expired_note_card_is_logged_without_its_text(caplog):
    caplog.set_level("INFO", logger="jarvis")
    model = FakeModel(use(call("remember", text="Likes xyzzy jazz")), say("Please confirm, sir."))
    a = brain.Assistant(chat=model)
    run(a, "Note that down")
    pid, request, made = a.pending
    a.pending = (pid, request, made - config.CONFIRM_TIMEOUT_SECONDS - 1)
    assert a.resolve_pending(pid, True).startswith("That request has expired")
    assert "confirmation expired unanswered" in caplog.text
    assert "xyzzy" not in caplog.text


def test_a_confirmation_just_inside_the_time_limit_still_works():
    a, events = _delete_turn()
    pid, request, made = a.pending
    a.pending = (pid, request, made - config.CONFIRM_TIMEOUT_SECONDS + 5)
    assert a.resolve_pending(pid, True) == "Done. The event has been deleted."


def test_reset_starts_a_new_conversation():
    a, events = _delete_turn()
    pid = events[-1]["confirm"]["id"]
    a.reset()
    assert [m["role"] for m in a.messages] == ["system"]
    assert a.resolve_pending(pid, True) == "That request has expired or was already handled."
    assert "Dentist" in jcal.get_events("2030-01-08")


# --- changing an event goes through the same confirmation ---------------------

def test_changing_an_event_waits_for_confirm_and_cancel_leaves_it():
    jcal.add_event("Dentist", "2030-01-08", "15:00")
    for approve, expected in ((False, "15:00-16:00 Dentist"), (True, "16:00-17:00 Dentist")):
        model = FakeModel(use(call("update_event", title="dentist", date="2030-01-08",
                                   new_start_time="16:00")), say("Please confirm, sir."))
        a = brain.Assistant(chat=model)
        events, _ = run(a, "Move the dentist to 4pm")
        step = next(e["step"] for e in events if e["type"] == "step")
        assert step["status"] == "waiting"
        assert "15:00-16:00 Dentist" in jcal.get_events("2030-01-08")      # not yet
        a.resolve_pending(events[-1]["confirm"]["id"], approve)
        assert expected in jcal.get_events("2030-01-08")
