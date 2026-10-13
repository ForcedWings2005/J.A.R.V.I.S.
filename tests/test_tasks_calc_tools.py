"""Tests for the to-do list (tasks.py), the calculator (calc.py) and the registry (tools.py)."""
import pytest

import brain  # noqa: F401  importing it registers every tool
import tasks
import tools
from calc import calculate

# ---------- to-do list ----------


def test_add_and_list_tasks():
    assert tasks.add_task("Buy milk") == "Added task 'Buy milk'."
    assert tasks.add_task("Essay", due="2030-01-11") == "Added task 'Essay', due 2030-01-11."
    assert tasks.list_tasks() == "Open tasks: Essay (due 2030-01-11); Buy milk"


def test_task_input_is_checked():
    assert tasks.add_task("   ").startswith("Error")
    assert tasks.add_task("Essay", due="Friday").startswith("Error")


def test_duplicate_open_task_is_rejected_but_a_done_one_can_return():
    tasks.add_task("Buy milk")
    assert tasks.add_task("buy MILK").startswith("Error")
    tasks.complete_task("milk")
    assert tasks.add_task("Buy milk").startswith("Added")


def test_complete_task_matches_part_of_the_title():
    tasks.add_task("Buy milk")
    assert tasks.complete_task("milk") == "Marked 'Buy milk' as done."
    assert tasks.list_tasks() == "No open tasks."


def test_complete_task_with_several_matches_asks():
    tasks.add_task("Call the bank")
    tasks.add_task("Call mum")
    assert "several" in tasks.complete_task("call")


def test_complete_task_matches_literally_not_as_a_pattern():
    tasks.add_task("50% off milk")
    tasks.add_task("Bread")
    assert tasks.complete_task("%").startswith("Marked '50% off milk'")
    assert tasks.complete_task("_").startswith("Error")


def test_checkbox_toggle():
    tasks.add_task("Buy milk")
    tid = tasks.tasks_list()[0]["id"]
    assert tasks.set_task_done(tid, True)
    assert tasks.tasks_list()[0]["done"] is True
    assert tasks.set_task_done(tid, False)
    assert not tasks.set_task_done(9999, True)


def test_open_tasks_come_first():
    tasks.add_task("Old")
    tasks.complete_task("Old")
    tasks.add_task("New")
    assert [t["title"] for t in tasks.tasks_list()] == ["New", "Old"]


# ---------- calculator ----------

@pytest.mark.parametrize("expr,result", [
    ("15 * 23 + 7", "15 * 23 + 7 = 352"),
    ("sqrt(144) / 3", "sqrt(144) / 3 = 4.0"),
    ("346 / 9", "346 / 9 = 38.4444444444"),
    ("2 ** 10", "2 ** 10 = 1024"),
    ("-pi", f"-pi = {-3.1415926536}"),
    ("round(2.5)", "round(2.5) = 2"),
])
def test_calculate(expr, result):
    assert calculate(expr) == result


@pytest.mark.parametrize("expr,error", [
    ("1 / 0", "division by zero"),
    ("(10**1000)**1000", "too large"),
    ("2 ** 1001", "too large"),
    ("10**300 * 10", "too large"),
    ("__import__('os').system('ls')", "could not evaluate"),
    ("open('jarvis.db')", "could not evaluate"),
    ("x + 1", "could not evaluate"),
    ("", "could not evaluate"),
])
def test_calculate_refuses_safely(expr, error):
    result = calculate(expr)
    assert result.startswith("Error") and error in result


# ---------- the registry ----------

def test_every_tool_is_registered_in_order():
    names = [s["function"]["name"] for s in tools.SCHEMAS]
    assert names == ["get_events", "add_event", "delete_event", "add_task",
                     "list_tasks", "complete_task", "calculate"]
    assert set(names) == set(tools.FUNCTIONS)


def test_required_arguments_come_from_the_function():
    schema = {s["function"]["name"]: s["function"]["parameters"] for s in tools.SCHEMAS}
    assert schema["add_event"]["required"] == ["title", "date", "start_time"]
    assert schema["delete_event"]["required"] == ["title"]
    assert "required" not in schema["list_tasks"]


def test_a_schema_that_does_not_match_the_function_is_refused():
    with pytest.raises(TypeError, match="differ"):
        @tools.tool("Broken", name={"type": "string"})
        def broken(title: str) -> str:
            return title


def test_a_name_cannot_be_registered_twice():
    with pytest.raises(ValueError, match="twice"):
        @tools.tool("Again", title={"type": "string"})
        def add_task(title: str) -> str:
            return title
