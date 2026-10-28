"""The open_space tool: JARVIS shows a space on screen, such as Work.

The model decides when the user means it, in any words (spec: "Switching is open-ended").
The tool only checks the name; the page does the switch when the turn streams a `space`
event. It changes only the view, so it needs no confirmation card.
Spec: docs/specs/2026-10-27-spaces-and-work.md ("Switching by voice, step by step").
"""
import config
from tools import ShowSpace, tool


@tool("Show one of the dashboard's spaces on screen. home is the welcome dashboard; work has "
      "the calendar, the to-do list and deadlines, for work, study and projects. Call it when "
      "the user wants to start working or studying, or asks for a space, in any words, such "
      "as 'let's get some work done' or 'time to study', and still answer the rest of their "
      "message. Do not call it when work is only mentioned, such as 'I had a long day at "
      "work'.",
      name={"type": "string", "enum": list(config.SPACES)})
def open_space(name: str) -> ShowSpace | str:
    wanted = str(name).strip().lower()
    if wanted not in config.SPACES:
        return f"Error: no space called '{str(name).strip()}'. Spaces: {', '.join(config.SPACES)}."
    return ShowSpace(wanted, f"Showing the {wanted.title()} space.")
