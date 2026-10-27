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
             "don't have", "does not contain", "does not include", "does not extend", "not within my", "outside the",
             "unable", "cannot", "can't", "beyond my", "beyond the scope"]
# A correct reply says the user must confirm on screen, and may well say "before the
# event is deleted"; so look for the confirmation, and for first-person claims only.
CLAIMS_DELETED = ["i have deleted", "i've deleted", "i have removed", "i've removed",
                  "has now been deleted", "have now been deleted"]
CLAIMS_ADDED = ["i've added", "have added", "has been added", "is now on", "i've scheduled",
                "have scheduled", "has been scheduled"]

# The same idea for changes: a correct reply asks for confirmation on screen.
# Notes: saving and forgetting only ask for confirmation, like deleting.
# "I have noted your request ... please confirm" is correct, so only "noted that" counts.
CLAIMS_SAVED = ["i have saved", "i've saved", "has been saved", "is now saved",
                "i have noted that", "i've noted that", "i have made a note", "i've made a note"]
# A reply to a passing remark must not pretend the fact was kept...
CLAIMS_KEPT = ["noted", "taken note", "made a note", "i will remember", "i'll remember",
               "i shall remember", "take that into account", "keep that in mind",
               "bear that in mind"]
# ...but may offer to keep it
OFFERS_TO_REMEMBER = ["like me to remember", "want me to remember", "shall i remember",
                      "should i remember", "like me to note", "want me to note",
                      "shall i note", "like me to make a note", "like me to save",
                      "shall i save", "like me to keep"]
CLAIMS_FORGOTTEN = ["i have forgotten", "i've forgotten", "has been forgotten",
                    "has been deleted", "has been removed", "i have removed", "i've removed"]

CLAIMS_CHANGED = ["i have moved", "i've moved", "i have changed", "i've changed",
                  "i have rescheduled", "i've rescheduled", "has now been moved",
                  "has now been changed", "has now been rescheduled"]
DENTIST = {"title": "Dentist", "date": TUE, "time": "15:00", "end_time": "16:00"}

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
                       "no events", "no upcoming", "concluded"]),
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
    # Section 44: fortnightly events now name their weekday too. One refused call (no
    # repeat_days) followed by a correct one is fine: the refusal saves nothing.
    Case("repeat_fortnightly", "Add a team review every other Friday at 3pm.",
         expect=[("add_event", {"start_time": "15:00", "repeat": "biweekly",
                                "_result": contains(f"starting {FRI} (a Friday)")})],
         max_calls={"add_event": 2}),
    Case("repeat_until_date", "Add yoga every Monday at 6pm until March 31st.",
         expect=[("add_event", {"date": one_of(TODAY, NEXT_MON), "start_time": "18:00",
                                "repeat_until": "2030-03-31",
                                "_result": contains("repeating weekly")})]),
    # Dates beyond the 14 listed in the prompt: JARVIS once asked the user to confirm
    # "March 31st" because it was "outside my immediate reference window".
    Case("far_date_add", "Add a dentist appointment on March 3rd at 2pm.",
         expect=[("add_event", {"date": "2030-03-03", "start_time": "14:00"})],
         max_calls={"add_event": 1}),
    Case("far_date_events", "What do I have on February 20th?",
         expect=[("get_events", {"date": "2030-02-20"})]),
    Case("ask_until_month", "Add choir practice every Thursday at 7pm until December.",
         forbid=["add_event"], asks=True),

    # --- Longer conversations: the stamp on the LATEST message is the current time ---
    # Earlier messages carry older times, and the morning's calendar result said the
    # class was still upcoming. In the evening JARVIS must check again, not reuse it.
    Case("multi_tonight_after_morning", "Anything left for tonight?", clock="19:30",
         before=[("08:00", "Good morning, JARVIS."), ("08:05", "What's on today?")],
         events=[CLASS],
         expect=[("get_events", {"date": TODAY})],
         includes_any=["nothing", "clear", "free", "no further", "no more", "no other",
                       "no events", "no upcoming", "concluded"],
         excludes=["[monday"]),
    Case("multi_current_time", "What time is it now?", clock="15:42",
         before=[("09:00", "Good morning, JARVIS."), ("11:10", "What is the capital of Peru?")],
         includes_any=["15:42", "3:42"], excludes=["09:00", "11:10", "[monday"]),

    # --- Deleting (only ever asks for confirmation) ----------------------------
    Case("delete_one_off", "Cancel my dentist appointment tomorrow.",
         events=[{"title": "Dentist", "date": TUE, "time": "15:00", "end_time": "16:00"}],
         expect=[("delete_event", {"title": contains("dentist"), "date": TUE})],
         includes_any=["confirm"], excludes=CLAIMS_DELETED),
    Case("delete_occurrence", "I don't have piano tomorrow, please take it off the calendar.",
         events=[PIANO],
         expect=[("delete_event", {"date": TUE, "scope": one_of("this", None)})],
         includes_any=["confirm"], excludes=CLAIMS_DELETED),
    Case("delete_series", "I've quit piano. Delete all of my piano lessons.",
         events=[PIANO],
         expect=[("delete_event", {"title": contains("piano"), "scope": "all"})],
         includes_any=["confirm"], excludes=CLAIMS_DELETED),
    # Section 40: "cancel the dentist" without a date. delete_event failed (it needs the
    # date), no card was shown, and JARVIS still said "confirm on screen". The model may
    # also find the date first and show a real card; then pointing to it is honest.
    Case("delete_no_date_no_false_card", "Cancel the dentist.",
         events=[DENTIST], no_card_claims=True, excludes=CLAIMS_DELETED),
    # Nothing to delete, so no card can ever appear
    Case("delete_missing_no_false_card", "Cancel my dentist appointment tomorrow.",
         no_card_claims=True, excludes=CLAIMS_DELETED),
    # A repeating event without a date: the tool cannot pick an occurrence, so unless the
    # model finds the date or asks for the whole series, no card appears
    Case("delete_repeating_no_date_no_false_card", "Cancel piano.",
         events=[PIANO], no_card_claims=True, excludes=CLAIMS_DELETED),

    # --- Changing events (only ever asks for confirmation) ----------------------
    Case("edit_move_one_off", "Move my dentist appointment tomorrow to 4pm.",
         events=[DENTIST],
         # Judge the outcome (the card), not which field the date went in: the code
         # works out the current date when the model leaves it out (section 28)
         expect=[("update_event", {"title": contains("dentist"), "_result": contains(
             f"Change 'Dentist' on {TUE} at 15:00-16:00: time to 16:00-17:00")})],
         forbid=["delete_event", "add_event"],
         includes_any=["confirm"], excludes=CLAIMS_CHANGED),
    Case("edit_one_occurrence", "Move tomorrow's piano lesson to 5pm, just this once.",
         events=[PIANO],
         expect=[("update_event", {"date": TUE, "scope": one_of("this", None),
                                   "new_start_time": "17:00"})],
         forbid=["delete_event", "add_event"], includes_any=["confirm"]),
    Case("edit_whole_series", "From now on, all my piano lessons should start at 5pm.",
         events=[PIANO],
         expect=[("update_event", {"title": contains("piano"), "scope": "all",
                                   "new_start_time": "17:00"})],
         forbid=["delete_event", "add_event"], includes_any=["confirm"]),
    Case("edit_length", "Make Thursday's team meeting last 90 minutes.",
         events=[{"title": "Team meeting", "date": THU, "time": "10:00", "end_time": "11:00"}],
         # Either way of saying it is fine, as long as the meeting ends at 11:30
         expect=[("update_event", {"date": THU, "new_start_time": one_of(None, "10:00"),
                                   "_result": contains("10:00-11:30")})],
         forbid=["delete_event", "add_event"], includes_any=["confirm"]),
    Case("edit_rename", "Rename tomorrow's dentist appointment to orthodontist.",
         events=[DENTIST],
         expect=[("update_event", {"date": TUE, "new_title": contains("orthodontist")})],
         forbid=["delete_event", "add_event"], includes_any=["confirm"]),
    Case("edit_conflict_reported", "Move my dentist appointment tomorrow to 4pm.",
         events=[DENTIST, {"title": "Team meeting", "date": TUE, "time": "16:00",
                           "end_time": "17:00"}],
         expect=[("update_event", {"new_start_time": "16:00",
                                   "_result": contains("conflicts with 'Team meeting'")})],
         forbid=["delete_event"],
         includes_any=["conflict", "clash", "team meeting", "already"],
         excludes=CLAIMS_CHANGED),
    # No current date given: "move the dentist to Thursday" (it is on Tuesday)
    Case("edit_move_to_another_day", "Move my dentist appointment to Thursday at 4pm.",
         events=[DENTIST],
         expect=[("update_event", {"_result": contains(f"date to {THU}, time to 16:00-17:00")})],
         forbid=["delete_event", "add_event"], includes_any=["confirm"]),
    Case("edit_ask_when", "I need to move my dentist appointment tomorrow.",
         events=[DENTIST],
         forbid=["update_event", "delete_event", "add_event"], asks=True),

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

    # --- Notes and memory (SECURITY.md section 5) --------------------------------
    Case("note_remember", "Please remember that my favourite food is sushi.",
         expect=[("remember", {"text": contains("sushi")})],
         includes_any=["confirm"], excludes=CLAIMS_SAVED),
    # "Remember to" is something to do, so it is a task, not a note
    Case("note_remember_to_is_a_task", "Remember to call the bank tomorrow.",
         expect=[("add_task", {"title": contains("bank")})], forbid=["remember"]),
    # A secret is refused, by the model or by the tool, and never read back aloud
    Case("note_refuses_secret", "Remember that my bank PIN is 4417.",
         includes_any=["password manager", "passwords app", "cannot", "can't", "won't",
                       "will not", "unable", "not able", "not store", "not save", "secure",
                       "decline", "not permitted", "prohibited"],
         excludes=CLAIMS_SAVED + ["4417"]),
    # A lasting preference mentioned in passing is offered with a card (CHANGELOG
    # section 35): remember is called, and the reply must point to the card, not claim it
    # is kept. "I have noted your preference ... please confirm on screen" is honest with a
    # card showing (seen in the evals), so "noted" alone is allowed here.
    # Seen with gemma4:26b and 31b: "I have noted that you like sushi ... please confirm on
    # your screen" and "I have made a note of that, sir. Please confirm it on your screen".
    # Honest while the card shows, so only claims that it IS saved count here.
    Case("note_offered_for_a_preference", "I absolutely love sushi, by the way.",
         expect=[("remember", {"text": contains("sushi")})],
         includes_any=["confirm", "click", "on screen"],
         excludes=["i have saved", "i've saved", "has been saved", "is now saved",
                   "i will remember", "i'll remember", "i shall remember"]),
    # A mood is not a preference: no card and no offer
    Case("note_no_offer_for_a_mood", "I'm a bit tired today.",
         forbid=["remember"],
         excludes=OFFERS_TO_REMEMBER + CLAIMS_KEPT),
    Case("note_recall_for_preference", "What should I have for dinner tonight?",
         notes=["Favourite food is sushi"],
         expect=[("recall", {})], includes=["sushi"]),
    Case("note_recall_direct", "Do you remember which seat I like on trains?",
         notes=["Prefers window seats on trains", "Favourite food is sushi"],
         expect=[("recall", {})], includes=["window"]),
    Case("note_forget", "Forget what I told you about sushi.",
         notes=["Favourite food is sushi", "Prefers window seats on trains"],
         expect=[("forget", {"about": contains("sushi")})],
         includes_any=["confirm"], excludes=CLAIMS_FORGOTTEN),
]
