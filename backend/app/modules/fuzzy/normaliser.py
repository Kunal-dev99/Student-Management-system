"""Query normaliser — Layer 1 of the fuzzy router.

Strips politeness fillers, expands contractions, collapses punctuation, and canonicalises
common time phrases so downstream matchers see a compact token stream. Pure function; no I/O.

Design rule: **normalisation must be conservative.** A word we drop here can never be a
scoring signal later, so we only drop tokens that are demonstrably filler across the whole
domain — never domain nouns or adjectives.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


# ---- Contractions ---------------------------------------------------------

CONTRACTIONS = {
    "haven't": "have not", "hasn't": "has not", "hadn't": "had not",
    "isn't": "is not", "aren't": "are not", "wasn't": "was not", "weren't": "were not",
    "don't": "do not", "doesn't": "does not", "didn't": "did not",
    "won't": "will not", "wouldn't": "would not", "shouldn't": "should not",
    "can't": "cannot", "couldn't": "could not",
    "who's": "who is", "what's": "what is", "there's": "there is",
    "it's": "it is", "let's": "let us", "that's": "that is",
    "i'm": "i am", "you're": "you are", "we're": "we are", "they're": "they are",
    "i've": "i have", "you've": "you have", "we've": "we have", "they've": "they have",
}


# ---- Politeness / filler tokens ------------------------------------------
#
# These are dropped after tokenisation. Verbs (see verbs.py) are dropped by the
# classifier, not here — this list is strictly for words that carry no meaning
# in any request phrasing.

FILLER_TOKENS = {
    "please", "plz", "pls", "kindly",
    "just", "simply", "quickly", "quick", "briefly",
    "would", "could", "can", "may", "might", "shall", "should",
    "for", "me", "us",
    "the", "a", "an", "some", "any",
    "actually", "really", "very",
    "hey", "hi", "hello", "ok", "okay",
    "am", "is", "are", "was", "were", "be", "been", "being",
    "do", "does", "did", "done", "have", "has", "had",
    # question chatter — the intent survives without it
    "let", "let me", "know",
}

# Two-word fillers stripped before token filtering (they'd otherwise be missed).
PHRASE_FILLERS = [
    "can you", "could you", "would you", "will you",
    "let me", "tell me", "let us know",
    "for me", "for us",
    "i want to", "i need to", "i would like to", "i'd like to",
    "please help",
]


# ---- Time-phrase canonicalisation ----------------------------------------
#
# These get replaced with a sentinel token the time parser recognises. Doing it here
# keeps the downstream classifier from being distracted by common phrasings.

TIME_PHRASES = [
    (r"\bthis (?:calendar )?year\b",            "period_thisyear"),
    (r"\blast (?:calendar )?year\b",            "period_lastyear"),
    (r"\bthis quarter\b",                       "period_thisquarter"),
    (r"\blast quarter\b",                       "period_lastquarter"),
    (r"\bthis month\b",                         "period_thismonth"),
    (r"\blast month\b",                         "period_lastmonth"),
    (r"\bnext month\b",                         "period_nextmonth"),
    (r"\bthis week\b",                          "period_thisweek"),
    (r"\blast week\b",                          "period_lastweek"),
    (r"\btoday\b",                              "period_today"),
    (r"\byesterday\b",                          "period_yesterday"),
    (r"\bytd\b",                                "period_thisyear"),
    (r"\bq1\b",                                 "period_q1"),
    (r"\bq2\b",                                 "period_q2"),
    (r"\bq3\b",                                 "period_q3"),
    (r"\bq4\b",                                 "period_q4"),
]


TOKEN_SPLIT = re.compile(r"[^a-z0-9_]+")


@dataclass(frozen=True)
class Normalised:
    original: str
    text: str              # canonicalised string (contractions expanded, punctuation stripped, time phrases replaced)
    tokens: tuple[str, ...]   # filler-free tokens in original order


def _expand_contractions(text: str) -> str:
    for k, v in CONTRACTIONS.items():
        text = text.replace(k, v)
    return text


def _apply_time_phrases(text: str) -> str:
    for pattern, sentinel in TIME_PHRASES:
        text = re.sub(pattern, sentinel, text)
    return text


def _strip_phrase_fillers(text: str) -> str:
    for phrase in PHRASE_FILLERS:
        text = re.sub(rf"\b{re.escape(phrase)}\b", " ", text)
    return text


def normalise(text: str) -> Normalised:
    """Turn raw user input into a canonical form plus a filler-free token list."""
    original = text or ""
    lower = original.strip().lower()
    lower = _expand_contractions(lower)
    lower = _apply_time_phrases(lower)
    lower = _strip_phrase_fillers(lower)
    # Collapse punctuation / whitespace into single spaces so token splitting is stable.
    collapsed = re.sub(r"\s+", " ", TOKEN_SPLIT.sub(" ", lower)).strip()
    raw_tokens = [t for t in collapsed.split() if t]
    tokens = tuple(t for t in raw_tokens if t not in FILLER_TOKENS)
    return Normalised(original=original, text=collapsed, tokens=tokens)
