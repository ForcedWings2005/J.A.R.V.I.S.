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
    assert steps == [{"text": "add_task(title=Buy milk)", "status": "done"}]
    assert [e["type"] for e in events].count("break") == 1
    tool_msg = model.seen[1][-1]
    assert tool_msg == {"role": "tool", "tool_name": "add_task", "content": "Added task 'Buy milk'."}


def test_several_tools_in_one_round():
    model = FakeModel(use(call("add_task", title="A"), call("add_task", title="B")), say("Both."))
    events, _ = run(brain.Assistant(chat=model), "Add A and B")
    assert sum(e["type"] == "step" for e in events) == 2
    assert len(tasks.tasks_list()) == 2


def test_tool_errors_are_marked_as_errors():
    model = FakeModel(use(call("complete_task", title="nothing")), say("No such task."))
    events, _ = run(brain.Assistant(chat=model), "Done with nothing")
    step = next(e["step"] for e in events if e["type"] == "step")
    assert step["status"] == "error"


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
    assert model.options == {"think": False, "keep_alive": "1h"}


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
