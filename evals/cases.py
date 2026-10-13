"""The eval cases. Each one comes from a request JARVIS should handle, most of them
from incidents in CHANGELOG.md.

Every case runs as if it were Monday 2030-01-07 (09:00 unless the case sets
`clock`), so the expected dates never change:

    Mon 01-07 (today)  Tue 01-08  Wed 01-09  Thu 01-10  Fri 01-11
    Sat 01-12  Sun 01-13  Mon 01-14
"""
from datetime import datetime

from evals.check import Case, between, contains, days, not_, one_of

NOW = datetime(2030, 1, 7, 9, 0)

TODAY, TUE, WED, THU, FRI = "2030-01-07", "2030-01-08", "2030-01-09", "2030-01-10", "2030-01-11"
NEXT_MON = "2030-01-14"

DONT_KNOW = ["not sure", "don't know", "do not know", "not certain", "outside my",
             "outside of my", "no information", "do not possess", "do not have",
             "don't have", "does not contain", "unable", "cannot", "can't", "beyond my"]
CLAIMS_DELETED = ["has been deleted", "have deleted", "i've deleted",
                  "has been removed", "i've removed", "have removed"]
CLAIMS_ADDED = ["i've added", "have added", "has been added", "is now on", "i've scheduled",
                "have scheduled", "has been scheduled"]

CLASS = {"title": "Biological anthropology class", "date": TODAY, "time": "10:00",
         "end_time": "11:15", "repeat": "weekly"}
PIANO = {"title": "Piano lesson", "date": TUE, "time": "16:00", "end_time": "17:00",
         "repeat": "weekly"}

CASES = [
    # --- No tools: chat and general knowledge -----------------------------------
    Case("greeting", "Good morning, JARVIS.", no_tools=True),
    Case("thanks", "Thank you, that's all for now.", no_tools=True),
    Case("general_knowledge", "What is the capital of Australia?",
         no_tools=True, includes=["Canberra"]),
    Case("admits_unknown", "Who won the 2029 World Series?",
         no_tools=True, includes_any=DONT_KNOW),

    # --- Calculator -------------------------------------------------------------
    # Numbers must stay as digits copied from the tool result. Spelled out in words, the
    # model got 7006652 wrong ("seven million sixty-six thousand ..."); speech_text.py
    # makes sure digits are spoken correctly. Commas in the reply are ignored.
    Case("calc_percent", "What is 17.5 percent of 2,340?",
         expect=[("calculate", {})], includes=["409.5"]),
    Case("calc_multiply", "What is 1234 times 5678?",
         expect=[("calculate", {})], includes=["7006652"]),
    Case("calc_divide", "What is 346 divided by 9?",
         expect=[("calculate", {})], includes=["38.4"]),
    Case("calc_large", "What is 98765 times 4321?",
         expect=[("calculate", {})], includes=["426763565"]),

    # --- Reading the calendar ---------------------------------------------------
    Case("events_tomorrow", "What do I have tomorrow?",
         expect=[("get_events", {"date": TUE})], forbid=["add_event"]),
    Case("events_friday", "Am I free on Friday?",
         expect=[("get_events", {"date": FRI})], forbid=["add_event"]),
    Case("events_week", "What does my week look like?",
         expect=[("get_events", {"date": TODAY, "end_date": between(FRI, NEXT_MON)})],
         max_calls={"get_events": 1}),
    # Section 16: a class that finished this morning was described as still ahead
    Case("tonight_nothing_left", "How are we looking tonight?", clock="19:30",
         events=[CLASS],
         expect=[("get_events", {"date": TODAY})],
         includes_any=["nothing", "clear", "free", "no further", "no more", "no other",
                       "no events", "concluded"]),
    Case("tonight_dinner", "Anything left for this evening?", clock="19:30",
         events=[CLASS, {"title": "Dinner with Sam", "date": TODAY, "time": "20:00",
                         "end_time": "21:30"}],
         expect=[("get_events", {"date": TODAY})], includes=["dinner"]),

    # --- Adding events ----------------------------------------------------------
    Case("add_default_hour", "Add a dentist appointment tomorrow at 3pm.",
         expect=[("add_event", {"title": contains("dentist"), "date": TUE,
                                "start_time": "15:00", "end_time": None})],
         max_calls={"add_event": 1}),
    Case("add_conflict_reported", "Add a dentist appointment tomorrow at 3pm.",
         events=[{"title": "Team meeting", "date": TUE, "time": "15:00", "end_time": "16:00"}],
         expect=[("add_event", {"date": TUE, "start_time": "15:00"})],
         includes_any=["conflict", "clash", "already", "overlap", "team meeting"],
         excludes=CLAIMS_ADDED),
    Case("add_duration", "Schedule a team meeting on Thursday at 10am for 75 minutes.",
         expect=[("add_event", {"date": THU, "start_time": "10:00", "end_time": "11:15"})]),
    Case("add_end_time", "Book the gym on Friday from 6pm to 7:30pm.",
         expect=[("add_event", {"date": FRI, "start_time": "18:00", "end_time": "19:30"})]),
    Case("ask_missing_time", "Add lunch with Alex on Wednesday.",
         forbid=["add_event"], asks=True),
    Case("ask_am_pm", "Put a call with the bank on Thursday at 8.",
         forbid=["add_event"], asks=True),

    # --- Repeating events -------------------------------------------------------
    # repeat="weekly" and repeat_days="tue" both save a weekly event, so these check
    # what add_event reports it saved rather than which argument the model used.
    Case("repeat_weekly", "Add piano lessons every Tuesday at 4pm.",
         expect=[("add_event", {"date": TUE, "start_time": "16:00",
                                "_result": contains("repeating weekly")})],
         max_calls={"add_event": 1}),
    # Section 14: "every Wednesday and Friday" was saved as every weekday
    Case("repeat_wed_fri", "I have biology class every Wednesday and Friday at 9am.",
         expect=[("add_event", {"start_time": "09:00", "repeat_days": days("wed", "fri"),
                                "repeat": not_("weekdays")})],
         max_calls={"add_event": 1}),
    Case("repeat_weekdays", "Add a standup every weekday at 9:30am.",
         expect=[("add_event", {"date": one_of(TODAY, TUE), "start_time": "09:30",
                                "repeat": "weekdays", "repeat_days": None})],
         max_calls={"add_event": 1}),
    Case("repeat_daily", "Add a daily walk at 7am, starting tomorrow.",
         expect=[("add_event", {"date": TUE, "start_time": "07:00", "repeat": "daily"})]),
    Case("repeat_until_date", "Add yoga every Monday at 6pm until March 31st.",
         expect=[("add_event", {"date": one_of(TODAY, NEXT_MON), "start_time": "18:00",
                                "repeat_until": "2030-03-31",
                                "_result": contains("repeating weekly")})]),
    Case("ask_until_month", "Add choir practice every Thursday at 7pm until December.",
         forbid=["add_event"], asks=True),

    # --- Deleting (only ever asks for confirmation) ----------------------------
    Case("delete_one_off", "Cancel my dentist appointment tomorrow.",
         events=[{"title": "Dentist", "date": TUE, "time": "15:00", "end_time": "16:00"}],
         expect=[("delete_event", {"title": contains("dentist"), "date": TUE})],
         includes_any=["confirm"], excludes=CLAIMS_DELETED),
    Case("delete_occurrence", "I don't have piano tomorrow, please take it off the calendar.",
         events=[PIANO],
         expect=[("delete_event", {"date": TUE, "scope": one_of("this", None)})],
         excludes=CLAIMS_DELETED),
    Case("delete_series", "I've quit piano. Delete all of my piano lessons.",
         events=[PIANO],
         expect=[("delete_event", {"title": contains("piano"), "scope": "all"})],
         excludes=CLAIMS_DELETED),

    # --- To-do list -------------------------------------------------------------
    Case("task_add", "Add buy milk to my to-do list.",
         expect=[("add_task", {"title": contains("milk")})], forbid=["add_event"]),
    Case("task_due", "I need to submit my essay by Friday.",
         expect=[("add_task", {"title": contains("essay"), "due": FRI})], forbid=["add_event"]),
    Case("task_list", "What's on my to-do list?",
         tasks=["Buy milk", "Call the bank"],
         expect=[("list_tasks", {})], includes=["milk", "bank"]),
    Case("task_complete", "I bought the milk.",
         tasks=["Buy milk"],
         expect=[("complete_task", {"title": contains("milk")})]),
]
