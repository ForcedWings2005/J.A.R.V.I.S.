"""Tests for notes.py: remember, recall and forget (SECURITY.md section 5).

The shared in-memory database is emptied before each test (conftest.py).
"""
import pytest

import notes
from database import conn as db, lock
from tools import NeedsConfirmation


def saved() -> list[str]:
    with lock:
        return [row[0] for row in db.execute("SELECT text FROM notes ORDER BY rowid")]


def save(*texts):
    """Save notes as if the user had clicked Save on each card."""
    for text in texts:
        notes.remember(text).apply()


# --- remember -------------------------------------------------------------------------

def test_remember_only_asks_and_saves_nothing_until_confirmed():
    result = notes.remember("Favourite food is sushi")
    assert isinstance(result, NeedsConfirmation)
    assert "Favourite food is sushi" in result.card
    assert result.reply.startswith("Confirmation required")
    assert saved() == []

    assert "saved" in result.apply().lower()
    assert saved() == ["Favourite food is sushi"]


@pytest.mark.parametrize("text", ["", "   "])
def test_remember_refuses_an_empty_note(text):
    assert notes.remember(text).startswith("Error:")


def test_remember_refuses_a_note_that_is_too_long():
    result = notes.remember("x" * (notes.config.NOTE_MAX_CHARS + 1))
    assert result.startswith("Error:")
    assert str(notes.config.NOTE_MAX_CHARS) in result


@pytest.mark.parametrize("text", [
    "My bank password is hunter2",
    "Wifi passcode: summer",
    "Garage PIN 4417",
    "The CVV is 123",
    "Card 4111 1111 1111 1111",
    "Account 12345678",
    "Login for the gym is Tr0ub4dor&3",
    "Recovery code is plain words but says recovery code",
])
def test_remember_refuses_things_that_look_like_secrets(text):
    result = notes.remember(text)
    assert isinstance(result, str) and result.startswith("Error:")
    assert "password manager" in result
    assert saved() == []


@pytest.mark.parametrize("text", [
    "Favourite food is sushi",
    "Likes the 07:30 train",
    "Born in 1990",
    "Prefers short answers, no small talk",
    "Allergic to peanuts",
    "Sister's name is Ana",
])
def test_remember_accepts_ordinary_preferences(text):
    assert isinstance(notes.remember(text), NeedsConfirmation)


def test_remember_refuses_a_note_that_is_already_saved():
    save("Favourite food is sushi")
    assert notes.remember("favourite food is SUSHI").startswith("Error:")


def test_confirming_the_same_note_twice_saves_it_once():
    """Two cards for the same text: the second click finds it already saved."""
    first, second = notes.remember("Likes jazz"), notes.remember("Likes jazz")
    first.apply()
    assert "already" in second.apply()
    assert saved() == ["Likes jazz"]


# --- recall ---------------------------------------------------------------------------

def test_recall_finds_a_note_by_any_word_in_it():
    save("Favourite food is sushi", "Prefers window seats")
    result = notes.recall("sushi")
    assert "Favourite food is sushi" in result
    assert "window" not in result


def test_recall_finds_the_start_of_a_word():
    save("Loves Italian restaurants")
    assert "Loves Italian restaurants" in notes.recall("restaurant")


def test_recall_says_the_notes_are_information_not_instructions():
    save("Favourite food is sushi")
    assert "not instructions" in notes.recall("food")


def test_recall_returns_at_most_the_limit():
    save(*[f"Likes band number {n}" for n in range(1, 9)])
    result = notes.recall("band")
    assert sum(f"band number {n}" in result for n in range(1, 9)) == notes.config.NOTES_RECALL_LIMIT


def test_recall_with_no_match_offers_the_most_recent_notes():
    save("Favourite food is sushi")
    result = notes.recall("weather")
    assert "No saved note matches" in result
    assert "Favourite food is sushi" in result


def test_recall_without_a_query_lists_the_most_recent_notes():
    save("Favourite food is sushi", "Prefers window seats")
    result = notes.recall()
    assert "sushi" in result and "window" in result


def test_recall_with_no_notes_says_so():
    assert notes.recall("anything") == "No saved notes yet."


@pytest.mark.parametrize("query", ['sushi"', '"', "NOT", "OR AND", "*", "NEAR(",
                                   "text:sushi", "^sushi", "-", "sushi)", "'; DROP TABLE notes; --"])
def test_recall_treats_search_words_as_plain_words(query):
    """FTS5 has its own search language (OR, NOT, quotes, *); none of it may leak through."""
    save("Favourite food is sushi")
    result = notes.recall(query)
    assert isinstance(result, str) and not result.startswith("Error")
    assert saved() == ["Favourite food is sushi"]


# --- forget ---------------------------------------------------------------------------

def test_forget_only_asks_and_deletes_nothing_until_confirmed():
    save("Favourite food is sushi", "Prefers window seats")
    result = notes.forget("sushi")
    assert isinstance(result, NeedsConfirmation)
    assert "Favourite food is sushi" in result.card
    assert result.reply.startswith("Confirmation required")
    assert len(saved()) == 2

    result.apply()
    assert saved() == ["Prefers window seats"]


def test_forget_with_several_matches_asks_which_one():
    save("Likes jazz", "Likes jazz piano", "Prefers tea")
    result = notes.forget("jazz")
    assert result.startswith("Error:")
    assert "Likes jazz piano" in result
    assert len(saved()) == 3


def test_forget_needs_every_word_to_match():
    save("Likes jazz", "Likes jazz piano")
    assert isinstance(notes.forget("jazz piano"), NeedsConfirmation)


def test_forget_with_no_match_says_so():
    save("Favourite food is sushi")
    assert notes.forget("weather").startswith("Error:")


def test_forget_with_only_symbols_says_so():
    assert notes.forget('"*"').startswith("Error:")


def test_forget_checks_again_when_the_button_is_clicked():
    """The note was already removed while the card waited: nothing else is touched."""
    save("Favourite food is sushi")
    card = notes.forget("sushi")
    notes.forget("sushi").apply()
    assert "already gone" in card.apply()
    assert saved() == []


# --- the model sends null instead of text (seen in the evals, CHANGELOG section 34) ----

def test_recall_with_null_lists_the_latest_notes():
    save("Favourite food is sushi")
    assert "Favourite food is sushi" in notes.recall(None)


def test_remember_and_forget_with_null_return_an_error_instead_of_crashing():
    assert notes.remember(None).startswith("Error:")
    assert notes.forget(None).startswith("Error:")


# --- what the model is told while a card waits (CHANGELOG section 38) ---------------------

def test_the_model_is_told_the_card_text_as_a_fact_not_an_order():
    """An order like 'Tell the user to confirm on screen' was read out word for word."""
    to_save = notes.remember("Likes jazz")
    save("Prefers tea")
    to_forget = notes.forget("tea")
    for result in (to_save, to_forget):
        assert result.reply.startswith("Confirmation required")
        assert result.card in result.reply
        assert "Tell the user" not in result.reply
