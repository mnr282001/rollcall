from __future__ import annotations

import re

# Ordered from most to least specific. Each captures a "names" blob that may
# contain more than one name (e.g. "Nayab and Sarah"), split apart below.
# The "what ... is/are/has/have" patterns use a greedy `.*` before the verb so
# that filler like "Jira tickets" ("what JIRA TICKETS is Nayab working on")
# is skipped rather than mistaken for part of the name.
_PATTERNS = [
    re.compile(r"\bwhat\b.*\b(?:is|are)\s+(?P<names>.+?)\s+(?:currently\s+)?working\s+on\b", re.IGNORECASE),
    re.compile(r"\bwhat\b.*\b(?:has|have)\s+(?P<names>.+?)\s+been\s+working\s+on\b", re.IGNORECASE),
    re.compile(r"\bactivity\s+for\s+(?P<names>.+?)\s*$", re.IGNORECASE),
    re.compile(r"\bfor\s+(?P<names>.+?)\s*$", re.IGNORECASE),
]

_SPLIT_CONNECTORS = re.compile(r"\s*,\s*(?:and\s+)?|\s+and\s+|\s*&\s*", re.IGNORECASE)

# Fallback: capitalized words that aren't sentence-leading question words.
_LEADING_QUESTION_WORDS = {"what", "show", "who", "how"}
_CAPITALIZED_WORD = re.compile(r"\b([A-Z][a-z]+)\b")


def _split_names(blob: str) -> list[str]:
    names = [part.strip().rstrip("'s") for part in _SPLIT_CONNECTORS.split(blob)]
    return [name for name in names if name]


def parse_names(question: str) -> list[str]:
    """Extracts the person/people's name(s) from a free-form question."""
    for pattern in _PATTERNS:
        match = pattern.search(question)
        if match:
            names = _split_names(match.group("names"))
            if names:
                return names

    candidates = [
        word for word in _CAPITALIZED_WORD.findall(question) if word.lower() not in _LEADING_QUESTION_WORDS
    ]
    return candidates
