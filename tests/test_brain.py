"""Tests for the assistant loop in brain.py, with a fake model.

The fake plays back scripted rounds: each round is some text and/or tool calls,
streamed in small chunks the way Ollama sends them.
"""
import ollama
import pytest

import brain
import jcal
import tasks
import tools


def call(name, **args):
    return ollama.Message.ToolCall(
        function=ollama.Message.ToolCall.Function(name=name, arguments=args)
    )


class FakeModel:
    """Stands in for ollama.chat. Each call to it plays the next scripted round."""

    def __init__(self, *rounds):
        self.rounds = list(rounds)
        self.seen = []          # the messages the model was shown, per round

    def __call__(self, model, messages, tools, stream):
        assert stream is True
        # copies, because the system message is updated in place every turn
        self.seen.append([dict(m) if isinstance(m, dict) else m for m in messages])
        if not self.rounds:
            raise AssertionError("the model was called more times than scripted")
        text, calls = self.rounds.pop(0)
        for i in range(0, len(text), 5):        # stream the text in pieces
            yield ollama.ChatResponse(message=ollama.Message(role="assistant", content=text[i:i + 5]))
        if calls:
            yield ollama.ChatResponse(message=ollama.Message(role="assistant", content="",
                                                             tool_calls=calls))


def say(text):
    return (text, [])


def use(*calls, text=""):
    return (text, list(calls))


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
    assert a.messages[-2] == {"role": "user", "content": "Good morning"}
    assert a.messages[-1].content == "Good morning, sir."


def test_the_conversation_continues_across_turns():
    model = FakeModel(say("Hello, sir."), say("You said hello."))
    a = brain.Assistant(chat=model)
    run(a, "Hello")
    run(a, "What did I say?")
    contents = [getattr(m, "content", None) or m.get("content") for m in model.seen[1]]
    assert "Hello" in contents and "Hello, sir." in contents


def test_system_prompt_is_rebuilt_every_turn(monkeypatch):
    model = FakeModel(say("One."), say("Two."))
    a = brain.Assistant(chat=model)
    monkeypatch.setattr(brain, "build_system_prompt", lambda: "PROMPT A")
    run(a, "first")
    monkeypatch.setattr(brain, "build_system_prompt", lambda: "PROMPT B")
    run(a, "second")
    assert model.seen[0][0]["content"] == "PROMPT A"
    assert model.seen[1][0]["content"] == "PROMPT B"


def test_no_text_at_all_gets_an_apology():
    a = brain.Assistant(chat=FakeModel(say("")))
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
