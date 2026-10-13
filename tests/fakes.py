"""A fake model for tests: plays back scripted rounds instead of calling Ollama."""
import ollama


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
