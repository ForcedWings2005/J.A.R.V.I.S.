"""The tool registry: each tool's function and its schema, written once, side by side.

    @tool("Mark a to-do item as finished, matched by its title.",
          title={"type": "string"})
    def complete_task(title: str) -> str:
        ...

Each keyword is one argument's JSON schema. Arguments without a default value are
required. The decorator refuses a schema whose arguments differ from the function's,
so the two can never drift apart.
"""
import inspect
from dataclasses import dataclass
from typing import Callable

FUNCTIONS: dict = {}    # name -> function
SCHEMAS: list = []      # what the model is shown, in registration order
PRIVATE: set = set()    # tools whose arguments and results the log records only as lengths
ASKS_FIRST: set = set() # tools that never act themselves: they return NeedsConfirmation


@dataclass
class NeedsConfirmation:
    """Returned by a tool that must not act until the user clicks Confirm."""
    card: str                   # the question on the confirmation card
    apply: Callable[[], str]    # runs on Confirm; returns what to tell the user
    reply: str                  # the tool result the model sees meanwhile
    private: bool = False       # if True, the log never records the card's text


def tool(description: str, **properties):
    def register(func):
        params = inspect.signature(func).parameters
        if set(params) != set(properties):
            raise TypeError(
                f"tool {func.__name__}: schema arguments {sorted(properties)} "
                f"differ from the function's {sorted(params)}"
            )
        required = [n for n, p in params.items() if p.default is inspect.Parameter.empty]
        parameters = {"type": "object", "properties": properties}
        if required:
            parameters["required"] = required
        if func.__name__ in FUNCTIONS:
            raise ValueError(f"tool {func.__name__} is registered twice")
        FUNCTIONS[func.__name__] = func
        SCHEMAS.append({
            "type": "function",
            "function": {"name": func.__name__, "description": description,
                         "parameters": parameters},
        })
        return func
    return register
