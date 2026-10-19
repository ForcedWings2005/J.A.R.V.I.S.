"""Run the eval suite against the real model (Ollama must be running).

    python -m evals                      every case, 3 runs each
    python -m evals --runs 1 -k delete   only cases whose name contains 'delete'
    python -m evals --model qwen3.5:latest
    python -m evals -v                   also print the reply and tool calls of failures

Each case runs through the real Assistant.chat_stream with a frozen clock and a
throwaway in-memory database, so your real calendar is never touched.
Results are saved to evals/results/ as JSON.
"""
import os

# Must happen BEFORE brain and jcal are imported, because they open the database on import
os.environ["JARVIS_DB"] = ":memory:"

import argparse  # noqa: E402
import contextlib  # noqa: E402
import hashlib  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from datetime import datetime  # noqa: E402
from pathlib import Path  # noqa: E402

import ollama  # noqa: E402

import brain  # noqa: E402
import database  # noqa: E402
import jcal  # noqa: E402
import tools  # noqa: E402
from evals.cases import CASES, NOW  # noqa: E402
from evals.check import check  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"


class Clock:
    now = NOW


class FakeDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        n = Clock.now
        return cls(n.year, n.month, n.day, n.hour, n.minute)


brain.datetime = FakeDateTime
jcal.datetime = FakeDateTime

# Every tool call the model makes in the current run, recorded and then run for real
calls = []
THINK = [None]          # set from --think in main()


class RecordingAssistant(brain.Assistant):
    def run_tool(self, call):
        result = super().run_tool(call)
        calls.append({"tool": call.function.name, "args": dict(call.function.arguments),
                      "result": result})
        return result


def set_clock(hhmm: str) -> None:
    h, m = map(int, hhmm.split(":"))
    Clock.now = NOW.replace(hour=h, minute=m)


def reset(case, model: str) -> brain.Assistant:
    """Fresh clock, database and conversation for one run."""
    set_clock(case.before[0][0] if case.before else case.clock)
    db = database.conn
    with database.lock:
        db.execute("DELETE FROM events")
        db.execute("DELETE FROM event_exceptions")
        db.execute("DELETE FROM tasks")
        db.execute("DELETE FROM notes")
        for ev in case.events:
            rd = ev.get("repeat_days")
            db.execute(
                "INSERT INTO events (title, date, time, end_time, repeat_rule, repeat_until, repeat_days) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (ev["title"], ev["date"], ev["time"], ev.get("end_time"),
                 ev.get("repeat", "none"), ev.get("repeat_until"),
                 ",".join(map(str, jcal._parse_days(rd))) if rd else None),
            )
        for title in case.tasks:
            db.execute("INSERT INTO tasks (title) VALUES (?)", (title,))
        for text in case.notes:
            db.execute("INSERT INTO notes (text, created) VALUES (?, ?)", (text, NOW.date().isoformat()))
        db.commit()
    calls.clear()
    return RecordingAssistant(model=model, think=THINK[0])


def run_once(case, model: str) -> dict:
    assistant = reset(case, model)
    # Earlier turns of a multi-turn case: real model, each at its own time, not scored
    for hhmm, message in case.before:
        set_clock(hhmm)
        for _ in assistant.chat_stream(message):
            pass
    calls.clear()
    set_clock(case.clock)
    reply, error = "", None
    start = time.perf_counter()
    with contextlib.redirect_stdout(io.StringIO()):  # brain prints every tool call
        for event in assistant.chat_stream(case.message):
            if event["type"] == "delta":
                reply += event["text"]
            elif event["type"] == "error":
                error = event["text"]
    seconds = time.perf_counter() - start
    failures = check(case, calls, reply)
    if error:
        failures.insert(0, f"stream error: {error}")
    return {"passed": not failures, "failures": failures, "reply": reply,
            "calls": list(calls), "seconds": round(seconds, 2)}


def model_id(name: str) -> str:
    for m in ollama.list().models:
        if m.model == name:
            return (m.digest or "")[:12] or "unknown"
    return "not pulled"


def prompt_hash() -> str:
    """Changes whenever the system prompt or a tool description changes."""
    Clock.now = NOW
    text = brain.build_system_prompt() + json.dumps(tools.SCHEMAS, sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m evals")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("-k", dest="filter", default="", help="only cases whose name contains this")
    ap.add_argument("--model", default=brain.config.MODEL)
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--think", choices=["default", "on", "off"], default="default",
                    help="gemma4's hidden reasoning before it answers")
    args = ap.parse_args()

    cases = [c for c in CASES if args.filter in c.name]
    if not cases:
        print(f"No case name contains {args.filter!r}.")
        return 1
    try:
        mid = model_id(args.model)
    except Exception as e:
        print(f"Cannot reach Ollama ({e}). Is it running?")
        return 1
    phash = prompt_hash()
    THINK[0] = {"default": brain.config.MODEL_THINK, "on": True, "off": False}[args.think]

    print(f"model {args.model} ({mid})  prompt {phash}  think {THINK[0]}  "
          f"{len(cases)} cases x {args.runs} runs\n")
    results, total_passed, started = [], 0, time.perf_counter()
    for case in cases:
        runs = [run_once(case, args.model) for _ in range(args.runs)]
        passed = sum(r["passed"] for r in runs)
        total_passed += passed
        avg = sum(r["seconds"] for r in runs) / len(runs)
        label = "PASS " if passed == len(runs) else "FAIL " if passed == 0 else "FLAKY"
        first = next((r["failures"][0] for r in runs if r["failures"]), "")
        print(f"{label} {passed}/{len(runs)}  {case.name:<24} {avg:5.1f}s  {first}")
        if args.verbose:
            for r in runs:
                if not r["passed"]:
                    made = ", ".join(f"{c['tool']}({c['args']})" for c in r["calls"]) or "none"
                    print(f"        tools: {made}\n        reply: {r['reply'].strip()}")
        results.append({"case": case.name, "message": case.message,
                        "passed": passed, "runs": runs})

    total = len(cases) * args.runs
    full = sum(1 for r in results if r["passed"] == args.runs)
    elapsed = time.perf_counter() - started
    print(f"\n{total_passed}/{total} runs passed ({100 * total_passed / total:.0f}%), "
          f"{full}/{len(cases)} cases passed every run, {elapsed / 60:.1f} min")

    RESULTS.mkdir(exist_ok=True)
    stamp = datetime.today().strftime("%Y-%m-%d_%H%M%S")
    out = RESULTS / f"{stamp}_{args.model.replace(':', '-')}.json"
    out.write_text(json.dumps({
        "date": stamp, "model": args.model, "model_id": mid, "prompt_hash": phash,
        "think": THINK[0],
        "runs_per_case": args.runs, "passed": total_passed, "total": total,
        "filter": args.filter, "results": results,
    }, indent=2))
    print(f"saved {out.relative_to(Path.cwd()) if out.is_relative_to(Path.cwd()) else out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
