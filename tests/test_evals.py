"""Tests for the eval suite's matching rules, and a sanity check of the cases.

The evals themselves need Ollama and only run on the Mac (python -m evals).
"""
import inspect

import pytest

import brain  # noqa: F401  importing it registers every tool
import tools
from evals.cases import CASES
from evals.check import Case, between, check, contains, days, not_, one_of


def call(tool, **args):
    return {"tool": tool, "args": args, "result": ""}


# --- check() -----------------------------------------------------------------

def test_matching_call_passes():
    case = Case("c", "m", expect=[("add_event", {"date": "2030-01-08", "start_time": "15:00"})])
    assert check(case, [call("add_event", date="2030-01-08", start_time="15:00")], "") == []


def test_wrong_argument_is_reported():
    case = Case("c", "m", expect=[("add_event", {"start_time": "15:00"})])
    failures = check(case, [call("add_event", start_time="03:00")], "")
    assert len(failures) == 1 and "start_time='03:00'" in failures[0]


def test_missing_call_is_reported():
    case = Case("c", "m", expect=[("get_events", {})])
    assert "no get_events call" in check(case, [], "")[0]


def test_values_compare_case_insensitively():
    case = Case("c", "m", expect=[("delete_event", {"scope": "all"})])
    assert check(case, [call("delete_event", scope=" ALL ")], "") == []


def test_none_means_argument_absent_or_empty():
    case = Case("c", "m", expect=[("add_event", {"end_time": None})])
    assert check(case, [call("add_event")], "") == []
    assert check(case, [call("add_event", end_time="")], "") == []
    assert check(case, [call("add_event", end_time="16:00")], "") != []


def test_a_later_call_can_match():
    """The model may make a mistake, read the error, and retry correctly."""
    case = Case("c", "m", expect=[("add_event", {"start_time": "15:00"})])
    calls = [call("add_event", start_time="3pm"), call("add_event", start_time="15:00")]
    assert check(case, calls, "") == []


def test_result_key_checks_the_tool_result():
    case = Case("c", "m", expect=[("add_event", {"_result": contains("repeating weekly")})])
    ok = {"tool": "add_event", "args": {"repeat_days": "tue"},
          "result": "Added 'Piano' ..., repeating weekly on Tue with no end date."}
    bad = {"tool": "add_event", "args": {}, "result": "Added 'Piano' starting 2030-01-08."}
    assert check(case, [ok], "") == []
    assert check(case, [bad], "") != []


def test_each_call_satisfies_only_one_expectation():
    case = Case("c", "m", expect=[("get_events", {}), ("get_events", {})])
    assert check(case, [call("get_events")], "") != []
    assert check(case, [call("get_events"), call("get_events")], "") == []


def test_no_tools_forbid_and_max_calls():
    assert check(Case("c", "m", no_tools=True), [call("get_events")], "") != []
    assert check(Case("c", "m", forbid=["add_event"]), [call("add_event")], "") != []
    capped = Case("c", "m", max_calls={"add_event": 1})
    assert check(capped, [call("add_event")], "") == []
    assert check(capped, [call("add_event"), call("add_event")], "") != []


def test_reply_checks():
    case = Case("c", "m", includes=["7006652"], includes_any=["sir", "madam"],
                excludes=["deleted"])
    assert check(case, [], "That is 7,006,652, sir.") == []
    assert len(check(case, [], "It was deleted.")) == 3


def test_reply_apostrophes_are_normalised():
    case = Case("c", "m", excludes=["i've added"])
    assert check(case, [], "I’ve added it.") != []


def test_asks():
    case = Case("c", "m", asks=True)
    assert check(case, [], "What time, sir?") == []
    assert check(case, [], "I will require a specific time, sir.") == []
    assert check(case, [], "Done. Lunch is booked.") != []


# --- predicates --------------------------------------------------------------

@pytest.mark.parametrize("value,ok", [
    ("wed,fri", True), ("Wednesday, Friday", True), ("fri wed", True),
    ("wed", False), ("mon,wed,fri", False), (None, False),
])
def test_days(value, ok):
    assert days("wed", "fri")(value) is ok


def test_other_predicates():
    assert contains("dentist")("Dentist appointment")
    assert not contains("dentist")(None)
    assert one_of("this", None)(None) and one_of("this", None)("this")
    assert not one_of("this", None)("all")
    assert between("2030-01-11", "2030-01-14")("2030-01-13")
    assert not between("2030-01-11", "2030-01-14")("2030-01-15")
    assert not_("weekdays")("weekly") and not not_("weekdays")("weekdays")


# --- the cases themselves ----------------------------------------------------

def _params(tool):
    for t in tools.SCHEMAS:
        if t["function"]["name"] == tool:
            return set(t["function"]["parameters"]["properties"])
    raise AssertionError(f"no schema for {tool}")


def test_case_names_are_unique():
    names = [c.name for c in CASES]
    assert len(names) == len(set(names))


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_case_refers_to_real_tools_and_arguments(case):
    for tool, spec in case.expect:
        assert tool in tools.FUNCTIONS
        func_args = set(inspect.signature(tools.FUNCTIONS[tool]).parameters)
        for arg in spec:
            if arg == "_result":
                continue
            assert arg in _params(tool), f"{tool} schema has no {arg}"
            assert arg in func_args, f"{tool} function has no {arg}"
    for tool in [*case.forbid, *case.max_calls]:
        assert tool in tools.FUNCTIONS
    times = [case.clock] + [t for t, _ in case.before]
    for hhmm in times:
        h, m = map(int, hhmm.split(":"))
        assert 0 <= h < 24 and 0 <= m < 60
    assert times[1:] == sorted(times[1:]) and all(t <= case.clock for t in times[1:]), \
        "earlier turns must be in time order, before the scored message"
