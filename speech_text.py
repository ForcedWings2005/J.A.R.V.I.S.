"""Text clean-up before speaking. Plain string work, so it is tested without Kokoro."""
import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

MAX_DECIMALS = 4  # "38.4444444444" is spoken as "38 point 4 4 4 4"

PRONUNCIATIONS = {
    "Hephaestus": "Heh-fess-tus",
    "Trastevere": "Trah-stay-veh-reh",
    "piazza": "pee-aht-sah",
}


def fix_pronunciations(text: str) -> str:
    for word, spoken in PRONUNCIATIONS.items():
        text = re.sub(rf"\b{re.escape(word)}\b", spoken, text, flags=re.IGNORECASE)
    return text


def _decimal(m: re.Match) -> str:
    whole, frac = m.group(1), m.group(2)
    if len(frac) > MAX_DECIMALS:
        rounded = Decimal(f"{whole}.{frac}").quantize(
            Decimal(1).scaleb(-MAX_DECIMALS), rounding=ROUND_HALF_UP
        )
        whole, _, frac = format(rounded, "f").partition(".")
        frac = frac.rstrip("0")
        if not frac:
            return whole
    return f"{whole} point " + " ".join(frac)


def speak_numbers(text: str) -> str:
    # "7,006,652" -> "7006652": commas inside a number are otherwise read as pauses
    text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", text)
    # espeak (Kokoro's phonemizer) takes a decimal point for a full stop when the text
    # also ends a sentence: "The result is 38.4444444444." is read "thirty-eight. four
    # billion four hundred ...". Writing the word "point" and the digits one by one
    # avoids it. Dotted strings like 1.2.3 are left alone.
    return re.sub(r"(?<![\d.])(\d+)\.(\d+)(?!\d|\.\d)", _decimal, text)


MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]


def _ordinal(n: int) -> str:
    """16 -> '16th', 1 -> '1st', 22 -> '22nd', 11/12/13 -> 'th'. Kokoro reads these well."""
    if 11 <= n % 100 <= 13:
        return f"{n}th"
    return f"{n}" + {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def speak_dates(text: str, today: date | None = None) -> str:
    """'2026-10-16' -> 'October the 16th' (the year only if it is not this year).

    Read as written, the speech model says "two thousand and twenty-six dash ten dash
    sixteen". Text that only looks like a date (2026-13-45) is left alone.
    """
    this_year = (today or date.today()).year

    def spoken(m: re.Match) -> str:
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return m.group(0)
        words = f"{MONTHS[d.month - 1]} the {_ordinal(d.day)}"
        return words if d.year == this_year else f"{words}, {d.year}"

    return re.sub(r"(?<![\d-])(\d{4})-(\d{2})-(\d{2})(?![\d-])", spoken, text)


def _spoken_time(h: int, m: int) -> str:
    """24-hour h:m as Kokoro reads it best: '3 pm', '3 30 pm', '9 oh 5 am', '12 noon'.

    Kokoro mumbles '3:30' and says 'zero' for '05', hence the spaces and 'oh'.
    """
    if (h, m) == (0, 0):
        return "midnight"
    if (h, m) == (12, 0):
        return "12 noon"
    suffix = "am" if h < 12 else "pm"
    h12 = h % 12 or 12
    if m == 0:
        return f"{h12} {suffix}"
    return f"{h12} {'oh ' if m < 10 else ''}{m} {suffix}"


_TIME = r"(?<![\d:])([01]?\d|2[0-3]):([0-5]\d)(?![\d:])(?:\s*([AaPp])\.?\s?[Mm]\b\.?)?"


def _to_24(h: str, m: str, ampm: str | None) -> tuple[int, int]:
    """'3', '00', 'p' -> (15, 0): respect an am/pm the model already wrote."""
    hour = int(h)
    if ampm and 1 <= hour <= 12:
        if ampm.lower() == "p" and hour < 12:
            hour += 12
        elif ampm.lower() == "a" and hour == 12:
            hour = 0
    return hour, int(m)


def speak_times(text: str) -> str:
    """'15:00' -> '3 pm', '15:00-16:30' -> '3 pm to 4 30 pm', '09:05' -> '9 oh 5 am'.

    Read as written, the speech model says "fifteen zero zero" and "zero nine zero five".
    """
    def one(m: re.Match) -> str:
        return _spoken_time(*_to_24(m.group(1), m.group(2), m.group(3)))

    def span(m: re.Match) -> str:
        first = _spoken_time(*_to_24(m.group(1), m.group(2), m.group(3)))
        second = _spoken_time(*_to_24(m.group(4), m.group(5), m.group(6)))
        return f"{first} to {second}"

    text = re.sub(_TIME + r"\s*[-–]\s*" + _TIME, span, text)   # ranges like 15:00-16:30
    return re.sub(_TIME, one, text)


def prepare(text: str, today: date | None = None) -> str:
    text = re.sub(r"[*_`#]", "", text).strip()
    text = speak_dates(text, today)      # before speak_numbers, which would read the digits
    text = speak_times(text)
    text = speak_numbers(text)
    return fix_pronunciations(text)
