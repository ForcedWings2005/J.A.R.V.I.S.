"""Speed figures for an eval run: which runs were slow, and which cases got slower.

One eval reply looped for 39 minutes and nothing said so until the end (CHANGELOG
sections 47 and 48). Pure functions on the saved results, so tests/test_evals.py checks
them in CI without a model. Timings depend on what else the Mac is doing, so these only
warn; they never fail a case.
"""
import json
from pathlib import Path
from statistics import median

SLOW_SECONDS = 30           # normal runs take 2 to 10 s; a capped runaway takes about 80
SLOWER_FACTOR = 1.5         # a case is "slower than last time" only if it is both 1.5 times
SLOWER_EXTRA_SECONDS = 3    # and 3 s slower, so tiny cases that wobble are not flagged
SLOWEST_SHOWN = 5


def is_slow(run: dict) -> bool:
    return run["seconds"] > SLOW_SECONDS


def _average(result: dict) -> float:
    return sum(r["seconds"] for r in result["runs"]) / len(result["runs"])


def summary(results: list) -> list:
    """Two lines: the medians, and the slowest runs with the tokens they wrote."""
    runs = [(res["case"], run) for res in results for run in res["runs"]]
    line = f"median run {median(run['seconds'] for _, run in runs):.1f}s"
    firsts = [run["first_word"] for _, run in runs if run.get("first_word") is not None]
    if firsts:                          # results saved before section 48 have no first_word
        line += f", first word {median(firsts):.1f}s"
    slowest = sorted(runs, key=lambda cr: cr[1]["seconds"], reverse=True)[:SLOWEST_SHOWN]
    parts = []
    for case, run in slowest:
        part = f"{case} {run['seconds']:.1f}s"
        if run.get("tokens") is not None:
            part += f" ({run['tokens']} tokens)"
        parts.append(part)
    return [line, "slowest: " + ", ".join(parts)]


def slower_cases(results: list, previous: dict) -> list:
    """Cases whose average time grew by both limits since the previous run."""
    before = {res["case"]: _average(res) for res in previous["results"] if res["runs"]}
    out = []
    for res in results:
        if res["case"] not in before or not res["runs"]:
            continue
        then, now = before[res["case"]], _average(res)
        if now >= then * SLOWER_FACTOR and now - then >= SLOWER_EXTRA_SECONDS:
            out.append(f"{res['case']} {then:.1f}s -> {now:.1f}s")
    return out


def previous_run(folder: Path, model: str):
    """The newest saved full run (no -k filter) of the same model, or None."""
    for path in sorted(Path(folder).glob("*.json"), reverse=True):    # names start with the date
        try:
            saved = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if saved.get("model") == model and not saved.get("filter"):
            saved["_file"] = path.name
            return saved
    return None
