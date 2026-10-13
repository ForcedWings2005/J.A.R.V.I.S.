"""Matching rules for eval cases.

Pure functions with no model and no database, so they are unit tested in CI
(tests/test_evals.py) even though the evals themselves only run on the Mac.
"""
import re
from dataclasses import dataclass, field


@dataclass
class Case:
    name: str
    message: str
    # Tool calls that must happen: (tool name, {argument: expected value}).
    # An expected value is a plain value (compared case-insensitively), None
    # (argument must be missing or empty), or a predicate made by the helpers below.
    # The special key "_result" checks the tool's result instead of an argument, for
    # when several argument combinations lead to the same correct outcome.
    expect: list = field(default_factory=list)
    forbid: list = field(default_factory=list)      # tools that must NOT be called
    no_tools: bool = False                          # no tool at all
    max_calls: dict = field(default_factory=dict)   # {tool: most calls allowed}
    includes: list = field(default_factory=list)    # reply must contain all of these
    includes_any: list = field(default_factory=list)  # reply must contain one of these
    excludes: list = field(default_factory=list)    # reply must contain none of these
    asks: bool = False                              # reply must ask for something (see ASKING)
    clock: str = "09:00"                            # time of day on NOW's date
    # Earlier messages in the same conversation, as ("HH:MM", message) pairs. They run
    # through the real model first, at their own times, and only the last one is scored.
    before: list = field(default_factory=list)
    events: list = field(default_factory=list)      # events in the calendar beforehand
    tasks: list = field(default_factory=list)       # open tasks beforehand


# JARVIS often asks politely without a question mark: "I will require a specific time."
ASKING = ["?", "require", "need", "clarify", "let me know", "please tell", "please specify",
          "please confirm", "could you", "would you", "advise"]


class Pred:
    """A named predicate, so failure messages say what was expected."""

    def __init__(self, fn, label: str):
        self.fn, self.label = fn, label

    def __call__(self, value) -> bool:
        return self.fn(value)

    def __repr__(self) -> str:
        return self.label


def _eq(expected, value) -> bool:
    if expected is None:
        return value in (None, "")
    if not isinstance(value, (str, int, float)):
        return False
    return str(value).strip().lower() == str(expected).strip().lower()


def contains(text: str) -> Pred:
    return Pred(lambda v: isinstance(v, str) and text.lower() in v.lower(), f"contains {text!r}")


def one_of(*values) -> Pred:
    return Pred(lambda v: any(_eq(x, v) for x in values), f"one of {values!r}")


def between(low: str, high: str) -> Pred:
    return Pred(lambda v: isinstance(v, str) and low <= v.strip() <= high, f"between {low} and {high}")


def not_(value) -> Pred:
    return Pred(lambda v: not _eq(value, v), f"not {value!r}")


def days(*names: str) -> Pred:
    """Weekday list in any spelling: 'wed,fri', 'Wednesday, Friday', ..."""
    want = {n[:3].lower() for n in names}

    def ok(v):
        if not isinstance(v, str):
            return False
        return {w[:3] for w in re.findall(r"[a-z]+", v.lower())} == want

    return Pred(ok, f"days {sorted(want)}")


def arg_mismatches(spec: dict, args: dict) -> list:
    out = []
    for key, want in spec.items():
        value = args.get(key)
        ok = want(value) if callable(want) else _eq(want, value)
        if not ok:
            out.append(f"{key}={value!r} (wanted {want!r})")
    return out


def _fmt(call: dict) -> str:
    args = ", ".join(f"{k}={v!r}" for k, v in call["args"].items())
    return f"{call['tool']}({args})"


def _norm(text: str) -> str:
    return text.lower().replace(",", "").replace("’", "'")


def check(case: Case, calls: list, reply: str) -> list:
    """Returns a list of failure reasons; empty means the run passed.

    calls: [{"tool": name, "args": {...}, "result": str}, ...] in order.
    """
    failures = []
    made = ", ".join(_fmt(c) for c in calls) or "no tools"

    if case.no_tools and calls:
        failures.append(f"expected no tools, got {made}")
    for c in calls:
        if c["tool"] in case.forbid:
            failures.append(f"forbidden call {_fmt(c)}")

    used = set()
    for tool, spec in case.expect:
        closest = None  # mismatches of the first call to the right tool, for the message
        for i, c in enumerate(calls):
            if i in used or c["tool"] != tool:
                continue
            miss = arg_mismatches(spec, {**c["args"], "_result": c["result"]})
            if not miss:
                used.add(i)  # each call can satisfy only one expectation
                break
            closest = closest or miss
        else:
            if closest:
                failures.append(f"{tool}: " + "; ".join(closest))
            else:
                failures.append(f"no {tool} call (got {made})")

    for tool, most in case.max_calls.items():
        n = sum(1 for c in calls if c["tool"] == tool)
        if n > most:
            failures.append(f"{tool} called {n} times (at most {most})")

    text = _norm(reply)
    for s in case.includes:
        if _norm(s) not in text:
            failures.append(f"reply lacks {s!r}")
    if case.includes_any and not any(_norm(s) in text for s in case.includes_any):
        failures.append(f"reply lacks any of {case.includes_any!r}")
    for s in case.excludes:
        if _norm(s) in text:
            failures.append(f"reply contains {s!r}")
    if case.asks and not any(s in text for s in ASKING):
        failures.append("reply does not ask for anything")
    return failures
